from django.conf import settings

from systems.plugins.index import BasePlugin
from utility.data import Collection, get_identifier, get_uuid, ensure_list, chunk_list

import billiard as multiprocessing
import time
import warnings


class BaseProvider(BasePlugin("qdrant_collection")):

    lock = multiprocessing.Lock()

    def __init__(self, type, name, command, **options):
        super().__init__(type, name, command)
        self.import_config(options)

        self.identifier = self._get_identifier()

        with self.lock:
            self.initialize(self)

    def _get_identifier(self):
        return get_identifier([self.name])

    @classmethod
    def initialize(cls, instance):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if not getattr(cls, "_client", None):
                cls._client = {}

            if instance.identifier not in cls._client:

                def init_client():
                    from qdrant_client import QdrantClient

                    cls._client[instance.identifier] = QdrantClient(
                        host=settings.QDRANT_HOST,
                        port=settings.QDRANT_PORT,
                        https=settings.QDRANT_HTTPS,
                        api_key=settings.QDRANT_ACCESS_KEY,
                        timeout=14400,
                    )

                if instance.command.debug:
                    init_client()
                else:
                    init_client()

                if not instance.client.collection_exists(instance.name):
                    instance._create_collection()

    @property
    def client(self):
        return self._client[self.identifier]

    def request(self, method, *args, **kwargs):
        from qdrant_client.http.exceptions import ResponseHandlingException

        wait = 1
        while True:
            try:
                return getattr(self.client, method)(*args, **kwargs)
            except ResponseHandlingException as e:
                self.command.warning(
                    "Request for Qdrant {} failed with: {}".format(method, e)
                )
                time.sleep(wait)
                wait = min(wait * 2, 300)

    def request_collection(self, name):
        return self.request("get_collection", name)

    def request_upsert(self, **kwargs):
        return self.request("upsert", **kwargs)

    def request_delete(self, **kwargs):
        return self.request("delete", **kwargs)

    def request_scroll(self, **kwargs):
        return self.request("scroll", **kwargs)

    def request_count(self, **kwargs):
        return self.request("count", **kwargs)

    def request_search(self, **kwargs):
        return self.request("search_batch", **kwargs)

    def _create_collection(self):
        from qdrant_client import models

        self.request(
            "recreate_collection",
            collection_name=self.name,
            shard_number=self.field_shards,
            vectors_config=models.VectorParams(
                size=self.field_dimension, distance=models.Distance.COSINE
            ),
        )
        self._create_collection_indexes()

    def _get_index_fields(self):
        # Override in subclass if needed
        return {}

    def _create_collection_indexes(self):
        for field_name, schema_type in self._get_index_fields().items():
            self.request(
                "create_payload_index",
                collection_name=self.name,
                field_name=field_name,
                field_schema=schema_type,
            )

    def _check_exists(self, filters):
        (result, offset) = self.request_scroll(
            collection_name=self.name,
            with_payload=["id"],
            with_vectors=False,
            scroll_filter=filters,
            limit=1,
        )
        if result:
            return True
        return False

    def _run_query(self, filters, fields=None, include_vectors=False):
        limit = 1000
        offset = None
        results = []

        while True:
            (page_result, offset) = self.request_scroll(
                collection_name=self.name,
                with_payload=ensure_list(fields) if fields else None,
                with_vectors=include_vectors,
                scroll_filter=filters,
                limit=limit,
                offset=offset,
            )
            results.extend(page_result)
            if not offset:
                break

        return results

    def filter(
        self, id_field, scoped_ids, fields=None, include_vectors=False, batch=500
    ):
        scoped_groups = chunk_list(ensure_list(scoped_ids), batch)

        for group_ids in scoped_groups:
            for record in self.get(
                **{
                    id_field: group_ids,
                    "fields": fields if fields else id_field,
                    "include_vectors": include_vectors,
                }
            ):
                yield record

    def _get_query_id_condition(self, name, ids):
        from qdrant_client import models

        return models.FieldCondition(
            key=name, match=models.MatchAny(any=ensure_list(ids))
        )

    def count(self, *ids):
        raise NotImplementedError("Method get must be implemented in subclasses")

    def exists(self, *ids):
        raise NotImplementedError("Method get must be implemented in subclasses")

    def get(self, *ids, **options):
        raise NotImplementedError("Method get must be implemented in subclasses")

    def _get_count_query(self, filters):
        count_data = self.request_count(
            collection_name=self.name, count_filter=filters, exact=True
        )
        return count_data.count

    def _get_record(self, sentence, embedding, **fields):
        from qdrant_client import models

        return models.PointStruct(
            id=get_uuid([sentence, *list(fields.values())]),
            vector=embedding,
            payload={"sentence": sentence, **fields},
        )

    def store(self, *fields, partition=None):
        raise NotImplementedError("Method store must be implemented in subclasses")

    def remove(self, **filters):
        raise NotImplementedError("Method remove must be implemented in subclasses")

    def remove_by_id(self, id):
        from qdrant_client import models

        return self.request_delete(
            collection_name=self.name,
            points_selector=models.PointIdsList(
                points=[id],
            ),
        )

    def search(
        self,
        embeddings,
        limit=10,
        fields=None,
        include_vectors=False,
        filter_field=None,
        filter_values=None,
        batch=100,
        min_score=0,
    ):
        from qdrant_client import models

        scoped_embeddings = chunk_list(embeddings, batch)
        search_results = []
        filters = None

        if filter_field and filter_values:
            filters = models.Filter(
                must=[self._get_query_id_condition(filter_field, filter_values)]
            )

        for embeddings in scoped_embeddings:
            search_queries = []
            for embedding in embeddings:
                search_queries.append(
                    models.SearchRequest(
                        vector=embedding,
                        filter=filters,
                        with_payload=ensure_list(fields) if fields else None,
                        with_vector=include_vectors,
                        limit=limit,
                        score_threshold=min_score,
                    )
                )

            search_results.extend(
                self.request_search(
                    collection_name=self.name, requests=search_queries, timeout=14400
                )
            )
        return search_results

    def get_info(self):
        collection = self.request_collection(self.name)

        def get_field_info(field):
            return {"type": field.data_type, "points": field.points}

        return Collection(
            status=collection.status.value,
            optimizer=collection.optimizer_status,
            vector_count=collection.vectors_count,
            indexed_vector_count=collection.indexed_vectors_count,
            point_count=collection.points_count,
            segment_count=collection.segments_count,
            schema={
                key: get_field_info(value)
                for key, value in collection.payload_schema.items()
            },
        )

    def list_snapshots(self):
        return sorted(
            self.request("list_snapshots", self.name),
            key=lambda snapshot: snapshot.creation_time,
            reverse=True,
        )

    def create_snapshot(self):
        return self.request("create_snapshot", self.name, wait=True)

    def delete_snapshot(self, name):
        return self.request("delete_snapshot", self.name, name, wait=True)

    def clean_snapshots(self, keep_num=3):
        keep_num = int(keep_num)
        success = True

        for index, snapshot in enumerate(self.list_snapshots()):
            if index >= keep_num:
                self.command.notice("Removing snapshot: {}".format(snapshot.name))
                if not self.delete_snapshot(snapshot.name):
                    success = False

        return success

    def restore_snapshot(self, name=None, priority="snapshot"):
        if not name:
            snapshots = self.list_snapshots()
            if not snapshots:
                return False
            name = snapshots[0].name

        return self.request(
            "recover_snapshot",
            self.name,
            "file:///qdrant/snapshots/{}/{}".format(self.name, name),
            priority=priority,
            wait=True,
        )
