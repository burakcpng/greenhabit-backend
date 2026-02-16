"""
Block System Tests — Apple Guideline 1.2 Compliance
Tests bidirectional blocking, idempotency, follow cleanup, and query helpers.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from pymongo.errors import DuplicateKeyError

# Import the module under test
from block_system import (
    is_blocked,
    get_all_blocked_ids,
    block_user,
    unblock_user,
    get_blocked_users_list,
)


# ======================== FIXTURES ========================

class MockCollection:
    """Lightweight mock for a MongoDB collection with unique index simulation."""
    
    def __init__(self, enforce_block_unique=False):
        self.docs = []
        self._unique_keys = set()  # Track (blockerUserId, blockedUserId) pairs
        self._enforce_block_unique = enforce_block_unique
    
    def insert_one(self, doc):
        if self._enforce_block_unique:
            key = (doc.get("blockerUserId"), doc.get("blockedUserId"))
            if key in self._unique_keys:
                raise DuplicateKeyError("Duplicate key error")
            self._unique_keys.add(key)
        doc["_id"] = f"mock_id_{len(self.docs)}"
        self.docs.append(doc)
        return MagicMock(inserted_id=doc["_id"])
    
    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None
    
    def find(self, query):
        results = [doc for doc in self.docs if self._matches(doc, query)]
        mock = MagicMock()
        mock.sort = MagicMock(return_value=results)
        mock.distinct = MagicMock(side_effect=lambda field: list(set(doc.get(field) for doc in results if doc.get(field))))
        mock.__iter__ = MagicMock(return_value=iter(results))
        return mock
    
    def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                removed = self.docs.pop(i)
                key = (removed.get("blockerUserId"), removed.get("blockedUserId"))
                self._unique_keys.discard(key)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)
    
    def delete_many(self, query):
        to_remove = [doc for doc in self.docs if self._matches(doc, query)]
        for doc in to_remove:
            self.docs.remove(doc)
            key = (doc.get("blockerUserId"), doc.get("blockedUserId"))
            self._unique_keys.discard(key)
        return MagicMock(deleted_count=len(to_remove))
    
    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                if "$addToSet" in update:
                    for field, value in update["$addToSet"].items():
                        if field not in doc:
                            doc[field] = []
                        if value not in doc[field]:
                            doc[field].append(value)
                if "$pull" in update:
                    for field, value in update["$pull"].items():
                        if field in doc and value in doc[field]:
                            doc[field].remove(value)
                if "$set" in update:
                    for field, value in update["$set"].items():
                        doc[field] = value
                return MagicMock(modified_count=1)
        if upsert:
            new_doc = {k: v for k, v in query.items() if not k.startswith("$")}
            if "$addToSet" in update:
                for field, value in update["$addToSet"].items():
                    new_doc[field] = [value]
            self.docs.append(new_doc)
            return MagicMock(modified_count=0, upserted_id="upserted")
        return MagicMock(modified_count=0)
    
    def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if self._matches(doc, query):
                if "$set" in update:
                    for field, value in update["$set"].items():
                        doc[field] = value
                count += 1
        return MagicMock(modified_count=count)
    
    def count_documents(self, query):
        return sum(1 for doc in self.docs if self._matches(doc, query))
    
    def create_index(self, *args, **kwargs):
        pass
    
    def _matches(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(doc, sub_q) for sub_q in value):
                    return False
            elif key == "$and":
                if not all(self._matches(doc, sub_q) for sub_q in value):
                    return False
            elif isinstance(value, dict):
                if "$nin" in value:
                    if doc.get(key) in value["$nin"]:
                        return False
                elif "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        return False
                elif "$ne" in value:
                    if doc.get(key) == value["$ne"]:
                        return False
                elif "$exists" in value:
                    if value["$exists"] and key not in doc:
                        return False
                    if not value["$exists"] and key in doc:
                        return False
            else:
                if doc.get(key) != value:
                    return False
        return True


@pytest.fixture
def db():
    """Create a mock database with all required collections."""
    mock_db = MagicMock()
    mock_db.user_blocks = MockCollection(enforce_block_unique=True)
    mock_db.follows = MockCollection()
    mock_db.users = MockCollection()
    mock_db.user_profiles = MockCollection()
    mock_db.task_shares = MockCollection()
    return mock_db


# ======================== is_blocked TESTS ========================

class TestIsBlocked:
    def test_no_blocks_returns_false(self, db):
        assert is_blocked(db, "user_a", "user_b") is False
    
    def test_forward_block_detected(self, db):
        db.user_blocks.insert_one({
            "blockerUserId": "user_a",
            "blockedUserId": "user_b",
            "createdAt": datetime.utcnow()
        })
        assert is_blocked(db, "user_a", "user_b") is True
    
    def test_reverse_block_detected(self, db):
        """Bidirectional: B blocks A → is_blocked(A, B) should be True"""
        db.user_blocks.insert_one({
            "blockerUserId": "user_b",
            "blockedUserId": "user_a",
            "createdAt": datetime.utcnow()
        })
        assert is_blocked(db, "user_a", "user_b") is True
    
    def test_self_check_returns_false(self, db):
        assert is_blocked(db, "user_a", "user_a") is False
    
    def test_empty_user_returns_false(self, db):
        assert is_blocked(db, "", "user_b") is False
        assert is_blocked(db, "user_a", "") is False
    
    def test_none_user_returns_false(self, db):
        assert is_blocked(db, None, "user_b") is False
    
    def test_unrelated_users_not_blocked(self, db):
        db.user_blocks.insert_one({
            "blockerUserId": "user_a",
            "blockedUserId": "user_c",
            "createdAt": datetime.utcnow()
        })
        assert is_blocked(db, "user_a", "user_b") is False


# ======================== get_all_blocked_ids TESTS ========================

class TestGetAllBlockedIds:
    def test_empty_returns_empty(self, db):
        assert get_all_blocked_ids(db, "user_a") == []
    
    def test_blocked_by_me(self, db):
        db.user_blocks.insert_one({
            "blockerUserId": "user_a",
            "blockedUserId": "user_b",
            "createdAt": datetime.utcnow()
        })
        result = get_all_blocked_ids(db, "user_a")
        assert "user_b" in result
    
    def test_blocked_me(self, db):
        db.user_blocks.insert_one({
            "blockerUserId": "user_b",
            "blockedUserId": "user_a",
            "createdAt": datetime.utcnow()
        })
        result = get_all_blocked_ids(db, "user_a")
        assert "user_b" in result
    
    def test_bidirectional_merged(self, db):
        """If A blocks B AND C blocks A, both B and C should be in the set."""
        db.user_blocks.insert_one({
            "blockerUserId": "user_a",
            "blockedUserId": "user_b",
            "createdAt": datetime.utcnow()
        })
        db.user_blocks.insert_one({
            "blockerUserId": "user_c",
            "blockedUserId": "user_a",
            "createdAt": datetime.utcnow()
        })
        result = get_all_blocked_ids(db, "user_a")
        assert set(result) == {"user_b", "user_c"}
    
    def test_empty_user_id(self, db):
        assert get_all_blocked_ids(db, "") == []


# ======================== block_user TESTS ========================

class TestBlockUser:
    def test_block_success(self, db):
        result = block_user(db, "user_a", "user_b")
        assert result["success"] is True
        assert is_blocked(db, "user_a", "user_b") is True
    
    def test_self_block_prevented(self, db):
        result = block_user(db, "user_a", "user_a")
        assert result["success"] is False
        assert "yourself" in result["message"].lower()
    
    def test_double_block_idempotent(self, db):
        result1 = block_user(db, "user_a", "user_b")
        result2 = block_user(db, "user_a", "user_b")
        assert result1["success"] is True
        assert result2["success"] is True
        assert result2.get("alreadyBlocked") is True
    
    def test_follows_removed_both_directions(self, db):
        """Blocking should remove follow relationships in BOTH directions."""
        db.follows.insert_one({"followerId": "user_a", "followedId": "user_b"})
        db.follows.insert_one({"followerId": "user_b", "followedId": "user_a"})
        
        block_user(db, "user_a", "user_b")
        
        assert db.follows.count_documents({"followerId": "user_a", "followedId": "user_b"}) == 0
        assert db.follows.count_documents({"followerId": "user_b", "followedId": "user_a"}) == 0
    
    def test_legacy_array_updated(self, db):
        """Should also write to legacy blockedUsers array for backward compat."""
        block_user(db, "user_a", "user_b")
        user = db.users.find_one({"userId": "user_a"})
        assert user is not None
        assert "user_b" in user.get("blockedUsers", [])
    
    def test_pending_shares_cancelled(self, db):
        """Blocking should cancel pending task shares between the users."""
        db.task_shares.insert_one({
            "senderId": "user_a",
            "recipientId": "user_b",
            "status": "pending"
        })
        db.task_shares.insert_one({
            "senderId": "user_b",
            "recipientId": "user_a",
            "status": "pending"
        })
        
        block_user(db, "user_a", "user_b")
        
        for share in db.task_shares.docs:
            assert share["status"] == "cancelled"
    
    def test_mutual_block(self, db):
        """Both users block each other — two separate docs, both directions blocked."""
        block_user(db, "user_a", "user_b")
        block_user(db, "user_b", "user_a")
        
        assert is_blocked(db, "user_a", "user_b") is True
        assert len(db.user_blocks.docs) == 2


# ======================== unblock_user TESTS ========================

class TestUnblockUser:
    def test_unblock_success(self, db):
        block_user(db, "user_a", "user_b")
        result = unblock_user(db, "user_a", "user_b")
        assert result["success"] is True
        assert is_blocked(db, "user_a", "user_b") is False
    
    def test_unblock_nonexistent(self, db):
        result = unblock_user(db, "user_a", "user_b")
        assert result["success"] is True  # Idempotent
    
    def test_unblock_only_one_direction(self, db):
        """Mutual block: unblocking A→B should NOT unblock B→A."""
        block_user(db, "user_a", "user_b")
        block_user(db, "user_b", "user_a")
        
        unblock_user(db, "user_a", "user_b")
        
        # B→A block should still exist
        assert is_blocked(db, "user_a", "user_b") is True  # Because B→A still exists
    
    def test_legacy_array_cleaned(self, db):
        block_user(db, "user_a", "user_b")
        unblock_user(db, "user_a", "user_b")
        
        user = db.users.find_one({"userId": "user_a"})
        if user:
            assert "user_b" not in user.get("blockedUsers", [])


# ======================== get_blocked_users_list TESTS ========================

class TestGetBlockedUsersList:
    def test_empty_list(self, db):
        result = get_blocked_users_list(db, "user_a")
        assert result == []
    
    def test_returns_blocked_user_details(self, db):
        # Add a profile for user_b
        db.user_profiles.insert_one({
            "userId": "user_b",
            "displayName": "EcoWarrior"
        })
        
        block_user(db, "user_a", "user_b")
        
        result = get_blocked_users_list(db, "user_a")
        assert len(result) == 1
        assert result[0]["userId"] == "user_b"
        assert result[0]["displayName"] == "EcoWarrior"
    
    def test_only_shows_users_i_blocked(self, db):
        """Should NOT include users who blocked me — only users I blocked."""
        block_user(db, "user_a", "user_b")
        block_user(db, "user_c", "user_a")  # C blocked me
        
        result = get_blocked_users_list(db, "user_a")
        user_ids = [u["userId"] for u in result]
        assert "user_b" in user_ids
        assert "user_c" not in user_ids
