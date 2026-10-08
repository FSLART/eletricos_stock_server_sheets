import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class EditingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.dict(os.environ, {'STORAGE_MODE': 'local', 'DB_PATH': str(Path(self.temp.name) / 'stock.db'), 'UPLOAD_DIR': str(Path(self.temp.name) / 'uploads')}):
            spec = importlib.util.spec_from_file_location('editing_server', ROOT / 'meu_servidor/app.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.client = self.module.app.test_client()
        self.client.post('/api/categories', json={'name': 'Test', 'props': ['code', 'size'], 'image': True})
        for code, size in [('A', 'small'), ('A', 'large')]:
            self.client.post('/api/move', json={'cat': 'Test', 'props': {'code': code, 'size': size}, 'qty': 4, 'mode': 'in'})

    def test_edit_item_preserves_identity_and_updates_stock(self):
        response = self.client.patch('/api/items/1', json={'props': {'code': 'B', 'size': 'small'}, 'qty': 0})
        self.assertEqual(response.status_code, 200, response.json)
        item = self.module.db_items()[0]
        self.assertEqual((item['id'], item['qty'], item['props']['code']), (1, 0, 'B'))

    def test_duplicate_and_invalid_item_edits_leave_original_untouched(self):
        original = self.module.db_items()
        for body, status in [
            ({'props': {'code': 'A', 'size': 'large'}, 'qty': 1}, 409),
            ({'props': {'code': 'B', 'size': 'small'}, 'qty': -1}, 400),
            ({'props': {'code': 'B', 'size': 'small'}, 'qty': 1.5}, 400),
            ({'props': {'code': ''}, 'qty': 1}, 400),
        ]:
            self.assertEqual(self.client.patch('/api/items/1', json=body).status_code, status)
            self.assertEqual(self.module.db_items(), original)

    def test_category_rename_and_field_rename_preserve_values_and_ids(self):
        response = self.client.patch('/api/categories/Test', json={
            'name': 'Renamed', 'image': True,
            'fields': [{'source': 'size', 'name': 'dimension'}, {'source': 'code', 'name': 'reference'}, {'source': None, 'name': 'note'}],
        })
        self.assertEqual(response.status_code, 200, response.json)
        items = self.module.db_items()
        self.assertEqual(items[0], {'id': 1, 'cat': 'Renamed', 'props': {'dimension': 'small', 'reference': 'A', 'note': ''}, 'qty': 4, 'image': ''})
        self.assertEqual(items[1]['id'], 2)

    def test_category_edit_collision_rolls_back_everything(self):
        original = self.module.db_items()
        response = self.client.patch('/api/categories/Test', json={
            'name': 'Renamed', 'image': False, 'fields': [{'source': 'code', 'name': 'code'}],
        })
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(self.module.db_items(), original)
        self.assertTrue(any(c['name'] == 'Test' for c in self.module.db_categories()))

    def test_category_name_conflict_and_missing_targets(self):
        self.client.post('/api/categories', json={'name': 'Other', 'props': ['code']})
        body = {'name': 'Other', 'image': True, 'fields': [{'source': 'code', 'name': 'code'}, {'source': 'size', 'name': 'size'}]}
        self.assertEqual(self.client.patch('/api/categories/Test', json=body).status_code, 409)
        self.assertEqual(self.client.patch('/api/categories/Missing', json=body).status_code, 404)
        self.assertEqual(self.client.patch('/api/items/999', json={'props': {}, 'qty': 0}).status_code, 404)

    def test_item_and_category_edits_preserve_images_unless_explicitly_removed(self):
        self.module.UPLOAD_DIR.mkdir()
        (self.module.UPLOAD_DIR / 'saved.jpg').write_bytes(b'test')
        with self.module.db_connection() as connection:
            connection.execute("UPDATE items SET image = '/uploads/saved.jpg' WHERE id = 1")
        body = {'props': {'code': 'B', 'size': 'small'}, 'qty': 2}
        self.assertEqual(self.client.patch('/api/items/1', json=body).status_code, 200)
        self.assertEqual(self.module.db_items()[0]['image'], '/uploads/saved.jpg')
        category = {'name': 'Test', 'image': False, 'fields': [{'source': p, 'name': p} for p in ['code', 'size']]}
        self.assertEqual(self.client.patch('/api/categories/Test', json=category).status_code, 200)
        self.assertEqual(self.module.db_items()[0]['image'], '/uploads/saved.jpg')
        self.assertEqual(self.client.patch('/api/items/1', json={**body, 'image': ''}).status_code, 200)
        self.assertEqual(self.module.db_items()[0]['image'], '')


if __name__ == '__main__':
    unittest.main()
