import sys
import os
from mle.utils.memory import LanceDBMemory

# Mock config to simulate None issue if needed
original_getcwd = os.getcwd

def test_memory_init_bug():
    # In buggy version, this should raise TypeError due to config None
    try:
        memory = LanceDBMemory(os.getcwd())
        # If no error, this is unexpected (fail test)
        assert False, "Expected TypeError due to None config"
    except TypeError as e:
        # Expected error
        assert "NoneType" in str(e)

    # If other error, show it too
    except Exception as e:
        assert False, f"Unexpected exception: {e}"

def test_memory_init_fixed():
    # This simulates fixed behavior, memory init should pass
    try:
        memory = LanceDBMemory(os.getcwd())
        # If no error, test pass
        assert True
    except Exception as e:
        assert False, f"Memory init failed after fix: {e}"

if __name__ == "__main__":
    test_memory_init_bug()
    test_memory_init_fixed()
    sys.exit(0)
