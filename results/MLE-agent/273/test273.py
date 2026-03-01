import sys
import mle.utils.memory as memory_mod
from mle.utils.memory import LanceDBMemory

class MonkeyPatch:
    def __init__(self):
        self.original = {}

    def setattr(self, target, name, value):
        self.original[(target, name)] = getattr(target, name, None)
        setattr(target, name, value)

    def undo(self):
        for (target, name), original_value in self.original.items():
            setattr(target, name, original_value)


def test_bug():
    mp = MonkeyPatch()
    mp.setattr(memory_mod, 'get_config', lambda x=None: None)
    try:
        LanceDBMemory('.')
        assert False, "Should raise an error with NoneType config"
    except TypeError as e:
        assert 'NoneType' in str(e), f"Unexpected error {e}"
    finally:
        mp.undo()


def test_fix():
    fixed_config = {"platform": "OpenAI", "api_key": "fake_key"}
    mp = MonkeyPatch()
    mp.setattr(memory_mod, 'get_config', lambda x=None: fixed_config)
    mem = LanceDBMemory('.')
    assert hasattr(mem, 'client'), "Missing client attribute"
    mp.undo()


def main():
    test_bug()
    test_fix()
    sys.exit(0)


if __name__ == "__main__":
    main()
