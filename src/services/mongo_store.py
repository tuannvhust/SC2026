"""
src/services/mongo_store.py
Client wrapper cho MongoDB Atlas (CRUD thuáº§n cho products vÃ  policies).
Chá»‰ Ä‘áº£m nháº­n viá»‡c Ä‘á»c/ghi dá»¯ liá»‡u, khÃ´ng chá»©a logic nghiá»‡p vá»¥ hay RAG.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

load_dotenv()


class MongoStore:
    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None
    ):
        self.uri = uri or os.getenv("MONGODB_URI")
        self.db_name = db_name or os.getenv("MONGODB_DB_NAME", "SC2026")
        self._client: Optional[MongoClient] = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            if not self.uri:
                raise ValueError("ChÆ°a thiáº¿t láº­p MONGODB_URI trong biáº¿n mÃ´i trÆ°á»ng hoáº·c .env")
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
        return self._client

    @property
    def db(self):
        return self.client[self.db_name]

    @property
    def products_col(self):
        return self.db["products"]

    @property
    def policies_col(self):
        return self.db["policies"]

    # =========================================================================
    # PRODUCTS CRUD
    # =========================================================================
    def get_product(self, sku: str) -> Optional[Dict[str, Any]]:
        """Láº¥y 1 sáº£n pháº©m theo SKU."""
        return self.products_col.find_one({"$or": [{"_id": sku}, {"sku": sku}]})

    def list_products(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Láº¥y danh sÃ¡ch táº¥t cáº£ sáº£n pháº©m hoáº·c theo bá»™ lá»c query."""
        return list(self.products_col.find(query or {}))

    def insert_product(self, doc: Dict[str, Any], upsert: bool = True) -> str:
        """ThÃªm má»›i hoáº·c cáº­p nháº­t 1 sáº£n pháº©m."""
        doc_id = doc.get("_id") or doc.get("sku")
        doc["_id"] = doc_id
        if upsert:
            self.products_col.replace_one({"_id": doc_id}, doc, upsert=True)
        else:
            self.products_col.insert_one(doc)
        return str(doc_id)

    def insert_products_bulk(self, docs: List[Dict[str, Any]]) -> int:
        """Náº¡p hÃ ng loáº¡t sáº£n pháº©m (Upsert)."""
        if not docs:
            return 0
        operations = []
        for doc in docs:
            doc_id = doc.get("_id") or doc.get("sku")
            doc["_id"] = doc_id
            operations.append(ReplaceOne({"_id": doc_id}, doc, upsert=True))
        result = self.products_col.bulk_write(operations)
        return result.matched_count + len(result.upserted_ids)

    def update_product(self, sku: str, update_dict: Dict[str, Any]) -> bool:
        """Cáº­p nháº­t cÃ¡c trÆ°á»ng thÃ´ng tin cá»§a sáº£n pháº©m."""
        res = self.products_col.update_one(
            {"$or": [{"_id": sku}, {"sku": sku}]},
            {"$set": update_dict}
        )
        return res.modified_count > 0

    def delete_product(self, sku: str) -> bool:
        """XÃ³a sáº£n pháº©m theo SKU."""
        res = self.products_col.delete_one({"$or": [{"_id": sku}, {"sku": sku}]})
        return res.deleted_count > 0

    # =========================================================================
    # POLICIES CRUD
    # =========================================================================
    def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """Láº¥y 1 chÃ­nh sÃ¡ch theo policy_id."""
        return self.policies_col.find_one({"$or": [{"_id": policy_id}, {"policy_id": policy_id}]})

    def list_policies(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Láº¥y danh sÃ¡ch táº¥t cáº£ cÃ¡c chÃ­nh sÃ¡ch."""
        return list(self.policies_col.find(query or {}))

    def insert_policy(self, doc: Dict[str, Any], upsert: bool = True) -> str:
        """ThÃªm má»›i hoáº·c cáº­p nháº­t 1 chÃ­nh sÃ¡ch."""
        doc_id = doc.get("_id") or doc.get("policy_id")
        doc["_id"] = doc_id
        if upsert:
            self.policies_col.replace_one({"_id": doc_id}, doc, upsert=True)
        else:
            self.policies_col.insert_one(doc)
        return str(doc_id)

    def insert_policies_bulk(self, docs: List[Dict[str, Any]]) -> int:
        """Náº¡p hÃ ng loáº¡t chÃ­nh sÃ¡ch (Upsert)."""
        if not docs:
            return 0
        operations = []
        for doc in docs:
            doc_id = doc.get("_id") or doc.get("policy_id")
            doc["_id"] = doc_id
            operations.append(ReplaceOne({"_id": doc_id}, doc, upsert=True))
        result = self.policies_col.bulk_write(operations)
        return result.matched_count + len(result.upserted_ids)

    def update_policy(self, policy_id: str, update_dict: Dict[str, Any]) -> bool:
        """Cáº­p nháº­t ná»™i dung chÃ­nh sÃ¡ch."""
        res = self.policies_col.update_one(
            {"$or": [{"_id": policy_id}, {"policy_id": policy_id}]},
            {"$set": update_dict}
        )
        return res.modified_count > 0

    def delete_policy(self, policy_id: str) -> bool:
        """XÃ³a chÃ­nh sÃ¡ch theo policy_id."""
        res = self.policies_col.delete_one({"$or": [{"_id": policy_id}, {"policy_id": policy_id}]})
        return res.deleted_count > 0
