from django.conf import settings

from settings.config import Config
from settings.core import ConfigurationError

#
# Qdrant Database
#
try:
    from settings.full import MANAGER

    QDRANT_HOST = Config.value("ZIMAGI_QDRANT_HOST")
    QDRANT_PORT = Config.value("ZIMAGI_QDRANT_PORT")
    QDRANT_ACCESS_KEY = Config.string("ZIMAGI_QDRANT_ACCESS_KEY")

    if not QDRANT_HOST or not QDRANT_PORT or not QDRANT_ACCESS_KEY:
        raise ConfigurationError(
            "ZIMAGI_QDRANT_HOST, ZIMAGI_QDRANT_PORT, and ZIMAGI_QDRANT_ACCESS_KEY environment variables required"
        )

    QDRANT_HTTPS = Config.boolean("ZIMAGI_QDRANT_HTTPS", False)

except Exception:
    pass

#
# QDRANT Configurations
#
QDRANT_DEFAULT_VECTOR_DIMENSION = Config.integer(
    "ZIMAGI_QDRANT_DEFAULT_VECTOR_DIMENSION", 768
)
