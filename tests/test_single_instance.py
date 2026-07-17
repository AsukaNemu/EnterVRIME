from __future__ import annotations

import unittest
import uuid

from enter_vr_ime.single_instance import SingleInstanceMutex


class SingleInstanceTests(unittest.TestCase):
    def test_second_mutex_is_rejected_until_first_closes(self) -> None:
        name = f"Local\\EnterVRIME.Test.{uuid.uuid4()}"
        first = SingleInstanceMutex(name)
        second = SingleInstanceMutex(name)
        third = SingleInstanceMutex(name)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(third.acquire())
        finally:
            first.close()
            second.close()
            third.close()


if __name__ == "__main__":
    unittest.main()
