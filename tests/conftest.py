import os
import sys
import tempfile
from pathlib import Path

# 테스트가 실제 data/ 폴더를 건드리지 않도록 import 전에 설정
os.environ.setdefault("EXAM_DATA_DIR", tempfile.mkdtemp(prefix="exam-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
