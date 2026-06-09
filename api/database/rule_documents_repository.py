from common.logger import get_logger
from typing import Any, Dict, List
from common.models import RuleDocument, DocumentRuleDocAssociation
from database.db_client import SQLiteClient
import json

logging = get_logger(__name__)


class RuleDocumentsRepository:
    def __init__(self, db_client: SQLiteClient) -> None:
        self.db_client = db_client

    async def init(self) -> None:
        await self.db_client.init_db()

    # ========== Rule Documents CRUD ==========

    async def get_all_rule_documents(self) -> List[RuleDocument]:
        logging.info("Retrieving all rule documents.")
        items = await self.db_client.retrieve_items_by_values("rule_documents", {})
        logging.info(f"Retrieved {len(items)} rule documents.")
        return [RuleDocument(**self._deserialize_doc(item)) for item in items]

    async def get_active_rule_documents(self) -> List[RuleDocument]:
        logging.info("Retrieving active rule documents.")
        items = await self.db_client.retrieve_items_by_values("rule_documents", {"status": "active"})
        return [RuleDocument(**self._deserialize_doc(item)) for item in items]

    async def get_rule_document(self, rule_doc_id: str) -> RuleDocument:
        item = await self.db_client.retrieve_item_by_id("rule_documents", rule_doc_id)
        if not item:
            raise ValueError(f"Rule document {rule_doc_id} not found.")
        return RuleDocument(**self._deserialize_doc(item))

    async def create_rule_document(self, doc: RuleDocument) -> RuleDocument:
        logging.info(f"Creating rule document: {doc.name}")
        await self.db_client.store_item("rule_documents", self._serialize_doc(doc))
        logging.info(f"Rule document {doc.id} created successfully.")
        return doc

    async def update_rule_document(self, rule_doc_id: str, fields: Dict[str, Any]) -> RuleDocument:
        logging.info(f"Updating rule document {rule_doc_id}")
        existing = await self.db_client.retrieve_item_by_id("rule_documents", rule_doc_id)
        if not existing:
            raise ValueError(f"Rule document {rule_doc_id} not found.")

        existing.update(fields)
        await self.db_client.store_item("rule_documents", self._serialize_doc_dict(existing))
        logging.info(f"Rule document {rule_doc_id} updated.")
        return RuleDocument(**self._deserialize_doc(existing))

    async def delete_rule_document(self, rule_doc_id: str) -> None:
        logging.info(f"Deleting rule document {rule_doc_id}")
        await self.db_client.delete_item("rule_documents", rule_doc_id)
        # Also delete document associations
        await self.db_client.delete_items_by_values("document_rule_documents", {"rule_document_id": rule_doc_id})
        logging.info(f"Rule document {rule_doc_id} deleted.")

    # ========== Document-RuleDocument Associations ==========

    async def get_document_rule_docs(self, doc_id: str) -> List[DocumentRuleDocAssociation]:
        logging.info(f"Retrieving rule document associations for document {doc_id}")
        items = await self.db_client.retrieve_items_by_values("document_rule_documents", {"doc_id": doc_id})
        return [DocumentRuleDocAssociation(
            doc_id=item["doc_id"],
            rule_document_id=item["rule_document_id"],
            enabled=bool(item["enabled"])
        ) for item in items]

    async def get_enabled_rule_docs_for_document(self, doc_id: str) -> List[RuleDocument]:
        """Get all rule documents that are enabled for a specific document."""
        logging.info(f"Retrieving enabled rule documents for document {doc_id}")
        query = """
            SELECT rd.* FROM rule_documents rd
            INNER JOIN document_rule_documents drd ON rd.id = drd.rule_document_id
            WHERE drd.doc_id = ? AND drd.enabled = 1 AND rd.status = 'active'
        """
        items = await self.db_client.execute_query(query, (doc_id,))
        docs = [RuleDocument(**self._deserialize_doc(item)) for item in items]
        logging.info(f"Found {len(docs)} enabled rule documents for document {doc_id}")
        return docs

    async def set_document_rule_doc(self, doc_id: str, rule_doc_id: str, enabled: bool) -> None:
        logging.info(f"Setting rule document {rule_doc_id} for document {doc_id}: enabled={enabled}")
        await self.db_client.store_item("document_rule_documents", {
            "doc_id": doc_id,
            "rule_document_id": rule_doc_id,
            "enabled": 1 if enabled else 0
        })

    async def delete_document_rule_docs(self, doc_id: str) -> None:
        logging.info(f"Deleting all rule document associations for document {doc_id}")
        await self.db_client.delete_items_by_values("document_rule_documents", {"doc_id": doc_id})

    # ========== Serialization ==========

    def _serialize_doc(self, doc: RuleDocument) -> Dict[str, Any]:
        data = doc.model_dump()
        for field in ["extracted_text", "parsed_rule_ids"]:
            if field in data and data[field] is not None:
                if isinstance(data[field], (list, dict)):
                    data[field] = json.dumps(data[field], ensure_ascii=False)
        return data

    def _serialize_doc_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(item)
        for field in ["extracted_text", "parsed_rule_ids"]:
            if field in out and out[field] is not None:
                if isinstance(out[field], (list, dict)):
                    out[field] = json.dumps(out[field], ensure_ascii=False)
        return out

    def _deserialize_doc(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if "parsed_rule_ids" in item and item["parsed_rule_ids"] and isinstance(item["parsed_rule_ids"], str):
            try:
                item["parsed_rule_ids"] = json.loads(item["parsed_rule_ids"])
            except Exception:
                item["parsed_rule_ids"] = []
        return item
