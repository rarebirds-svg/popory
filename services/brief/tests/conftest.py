# tests에서 send_gmail / fetch_subscribers / publish_to_portal 같은 루트 CLI 모듈을 import 하기 위함.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
