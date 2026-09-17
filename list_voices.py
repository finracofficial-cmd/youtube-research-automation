"""ElevenLabs の声を一覧する。make.py --voice に渡す voice_id を選ぶのに使う。

  ELEVENLABS_API_KEY=... python3 list_voices.py
"""
from assets.tts import voices

for v in voices():
    lab = v.get("labels") or {}
    tags = " / ".join(f"{k}={val}" for k, val in lab.items() if val)
    print(f"{v['voice_id']}  {v['name']:<22} {tags}")
