"""Data model for MemState on Kuzu (entities, properties, mappers)."""

from memstate.datamodel.constants import (
    LABEL_TOPIC,
    PROP_EMBEDDING,
    PROP_FAILED_SALIENCE,
    PROP_FIELDS_JSON,
    PROP_TOPIC_HISTORY_JSON,
    PROP_TOPIC_KIND,
    VECTOR_INDEX_ATTRIBUTE,
    VECTOR_INDEX_LABEL,
)
from memstate.datamodel.field import FieldHeadNode, FieldVersionNode, FieldWithHistory
from memstate.datamodel.fields import (
    FieldHistoryEntry,
    FieldType,
    TopicField,
    TopicFields,
    new_history_entry,
)
from memstate.datamodel.mappers import topic_from_graph_row, topic_history_to_json
from memstate.datamodel.topic import TopicHistoryEvent, TopicNode

FIELD_CHAIN = (
    "(Topic)-[:HAS_FIELD]->(FieldHead)-[:LATEST]->(FieldVersion)-[:PREV*0..]->..."
)

__all__ = [
    "FIELD_CHAIN",
    "FieldHeadNode",
    "FieldHistoryEntry",
    "FieldType",
    "FieldVersionNode",
    "FieldWithHistory",
    "LABEL_TOPIC",
    "PROP_EMBEDDING",
    "PROP_FAILED_SALIENCE",
    "PROP_FIELDS_JSON",
    "PROP_TOPIC_HISTORY_JSON",
    "PROP_TOPIC_KIND",
    "VECTOR_INDEX_ATTRIBUTE",
    "VECTOR_INDEX_LABEL",
    "TopicField",
    "TopicFields",
    "TopicHistoryEvent",
    "TopicNode",
    "new_history_entry",
    "topic_from_graph_row",
    "topic_history_to_json",
]
