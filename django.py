from django.conf import settings

from settings.config import Config

#
# Qdrant Database
#
try:
  from settings.full import MANAGER

  qdrant_service = MANAGER.get_service('qdrant')
  qdrant_service_port = qdrant_service['ports']['6333/tcp'] if qdrant_service else None

  if qdrant_service:
    qdrant_host = '127.0.0.1'
    qdrant_port = qdrant_service_port
  else:
    qdrant_host = None
    qdrant_port = None

  _qdrant_host = Config.value('ZIMAGI_QDRANT_HOST', None)
  if _qdrant_host:
    qdrant_host = _qdrant_host

  _qdrant_port = Config.value('ZIMAGI_QDRANT_PORT', None)
  if _qdrant_port:
    qdrant_port = _qdrant_port

  if not qdrant_host or not qdrant_port:
    raise ConfigurationError("ZIMAGI_QDRANT_HOST and ZIMAGI_QDRANT_PORT environment variables required")

  QDRANT_HOST = qdrant_host
  QDRANT_PORT = qdrant_port
  QDRANT_ACCESS_KEY = Config.string('ZIMAGI_QDRANT_ACCESS_KEY')
  QDRANT_HTTPS = Config.boolean('ZIMAGI_QDRANT_HTTPS', False)

except Exception:
  pass

#
# QDRANT Configurations
#
QDRANT_DEFAULT_VECTOR_DIMENSION = Config.integer('ZIMAGI_QDRANT_DEFAULT_VECTOR_DIMENSION', 768)
