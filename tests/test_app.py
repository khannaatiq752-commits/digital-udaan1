import os
import tempfile
import unittest
from pathlib import Path

class DigitalUdaanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(Path(self.temp.name) / "test.sqlite3")
        os.environ["FLASK_SECRET_KEY"] = "test-secret-key-not-for-production"
        import app as app_module
        app_module.DATABASE = Path(self.temp.name) / "test.sqlite3"
        app = app_module.app
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.app = app
        with app.app_context():
            app_module.init_db()
        self.client = app.test_client()

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("FLASK_SECRET_KEY", None)

    def test_home_and_catalogue(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/courses")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Digital Marketing Foundations", response.data)

    def test_register_and_dashboard(self):
        response = self.client.post("/register", data={
            "name": "Test Student", "email": "student@example.com", "password": "safe-password-123",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Learning paths", response.data)

    def test_admin_denied_when_signed_out(self):
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_course_detail(self):
        with self.app.app_context():
            from app import get_db
            course = get_db().execute("SELECT slug FROM courses LIMIT 1").fetchone()
        self.assertEqual(self.client.get("/courses/" + course["slug"]).status_code, 200)

if __name__ == "__main__":
    unittest.main()
