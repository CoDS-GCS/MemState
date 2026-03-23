"""Graph labels, relationship types, and property keys for MemState (Kuzu)."""

LABEL_TOPIC = "Topic"
LABEL_FIELD_HEAD = "FieldHead"
LABEL_FIELD_VERSION = "FieldVersion"
LABEL_META = "MemStateMeta"

REL_HAS_FIELD = "HAS_FIELD"
REL_LATEST = "LATEST"
REL_PREV = "PREV"
REL_RELATED = "RELATED"

# Topic scalar properties (native vector on `PROP_EMBEDDING`)
PROP_ID = "id"
PROP_TITLE = "title"
PROP_SUMMARY = "summary"
PROP_SALIENCE = "salience"
PROP_FAILED_SALIENCE = "failed_salience"
PROP_ARCHIVED = "archived"
PROP_CREATED_AT = "created_at"
PROP_UPDATED_AT = "updated_at"
PROP_TOPIC_HISTORY_JSON = "topic_history_json"
PROP_TOPIC_KIND = "topic_kind"
PROP_FIELDS_JSON = "fields_json"
PROP_EMBEDDING = "embedding"
# Legacy / fallback for engines or rows that only expose JSON
PROP_EMBEDDING_JSON = "embedding_json"

# Field head / version
FH_PROP_TOPIC_ID = "topic_id"
FH_PROP_FIELD_NAME = "field_name"
FV_PROP_ID = "id"
FV_PROP_VALUE = "value"
FV_PROP_VALID_FROM = "valid_from"
FV_PROP_PROVENANCE = "provenance"

VECTOR_INDEX_LABEL = LABEL_TOPIC
VECTOR_INDEX_ATTRIBUTE = PROP_EMBEDDING
