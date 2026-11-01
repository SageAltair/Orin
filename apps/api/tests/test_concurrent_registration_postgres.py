"""PostgreSQL regression: two fresh users can register against an empty capability catalog."""
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from orin_api.auth import register_user
from orin_api.database import Base
from orin_api.schemas import RegisterRequest


@unittest.skipUnless(os.getenv("ORIN_FOCUS_TEST_DATABASE_URL"), "requires explicitly isolated PostgreSQL")
class ConcurrentRegistrationPostgresTests(unittest.TestCase):
    def test_two_registrations_initialize_capabilities_without_conflict(self):
        source = make_url(os.environ["ORIN_FOCUS_TEST_DATABASE_URL"])
        self.assertEqual(source.get_backend_name(), "postgresql")
        self.assertIn(source.host, {"localhost", "127.0.0.1", "db"})
        name = "orin_signup_test_" + uuid.uuid4().hex[:12]
        admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
        engine = None
        try:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            engine = create_engine(source.set(database=name), pool_pre_ping=True)
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine)
            barrier = threading.Barrier(2)
            thread_state = threading.local()

            def synchronize_empty_catalog(conn, cursor, statement, parameters, context, executemany):
                if (threading.current_thread().name.startswith("registration")
                        and "FROM capabilities" in statement
                        and not getattr(thread_state, "synced", False)):
                    thread_state.synced = True
                    barrier.wait(timeout=20)

            event.listen(engine, "after_cursor_execute", synchronize_empty_catalog)

            def register(index):
                with sessions() as session:
                    try:
                        user = register_user(RegisterRequest(
                            display_name=f"Concurrent registration {index}",
                            email=f"isolated-{index}-{uuid.uuid4().hex}@example.com",
                            password="Disposable-Registration-2026-Strong!",
                        ), session)
                        return user.email
                    except HTTPException as exc:
                        return exc.status_code

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="registration") as pool:
                results = list(pool.map(register, (1, 2)))
            self.assertTrue(all(isinstance(item, str) and "@example.com" in item
                                for item in results), f"Concurrent signup results: {results}")
        finally:
            if engine is not None:
                engine.dispose()
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            admin.dispose()


if __name__ == "__main__":
    unittest.main()
