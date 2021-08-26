import pytest
import os


@pytest.fixture(autouse=True)
def cleanup():
     
     log_path = os.path.join(os.path.dirname(__file__), 'test_data', "jama_exec.log")
     if os.path.exists(log_path):
          os.remove(log_path)
     