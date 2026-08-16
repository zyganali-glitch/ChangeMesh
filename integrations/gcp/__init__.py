"""Google Cloud Platform provider integrations.

Contains Pub/Sub, Firestore, and Vertex AI adapters.
Imports of google.cloud are strictly bounded to this package.
"""

from integrations.gcp.pubsub_adapter import (
    GooglePubSubConsumer,
    GooglePubSubPublisher,
)
from integrations.gcp.firestore_adapter import (
    GoogleFirestoreSagaRepository,
)

__all__ = [
    "GooglePubSubConsumer",
    "GooglePubSubPublisher",
    "GoogleFirestoreSagaRepository",
]
