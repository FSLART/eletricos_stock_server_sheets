import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class LocalStorageTest(unittest.TestCase):
    def test_local_crud_survives_reload_without_google_or_excel(self):
        for index, relative in enumerate([
            'meu_servidor/app.py',
            'serverstocklart-main/meu_servidor/app.py',
        ]):
            with self.subTest(server=relative), tempfile.TemporaryDirectory() as temp:
                with patch.dict(os.environ, {
                    'STORAGE_MODE': 'local',
                    'DB_PATH': str(Path(temp) / 'stock.db'),
                    'EXCEL_PATH': str(Path(temp) / 'stock.xlsx'),
                    'UPLOAD_DIR': str(Path(temp) / 'uploads'),
                }):
                    spec = importlib.util.spec_from_file_location(f'local_stock_{index}', ROOT / relative)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                with patch.object(module, 'sync_google_to_db', side_effect=AssertionError('Google called')), \
                     patch.object(module, 'sync_excel_to_db', side_effect=AssertionError('Excel called')), \
                     patch.object(module, 'save_google_items', side_effect=AssertionError('Google called')):
                    client = module.app.test_client()
                    response = client.get('/api/data')
                    self.assertEqual(response.status_code, 200, response.json)
                    self.assertEqual(client.post('/api/categories', json={
                        'name': 'Local test', 'props': ['reference'], 'image': True,
                    }).status_code, 200)
                    self.assertEqual(client.post('/api/move', json={
                        'cat': 'Local test', 'props': {'reference': 'ABC'}, 'qty': 4, 'mode': 'in',
                    }).status_code, 200)
                    data = client.get('/api/data').json
                    item = next(i for i in data['items'] if i['cat'] == 'Local test')
                    self.assertEqual(item['qty'], 4)
                    self.assertEqual(client.post(f"/api/items/{item['id']}/step", json={'delta': 2}).status_code, 200)
                    # Read through another connection to verify persistent storage.
                    self.assertEqual(module.db_items()[0]['qty'], 6)
                    self.assertFalse(module.EXCEL_PATH.exists())
                    self.assertEqual(client.delete('/api/categories/Local test').status_code, 200)
                    final = client.get('/api/data').json
                    self.assertFalse(any(c['name'] == 'Local test' for c in final['categories']))
                    self.assertEqual(final['items'], [])


if __name__ == '__main__':
    unittest.main()
