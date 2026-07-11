# claude 출력에서 <reply> 또는 <skip> 하나만 추출하는 답글 초안 계약.
import re

from popory_content.contract import ContractError


def parse_reply(text: str) -> dict:
    reply_m = re.search(r"<reply>(.*?)</reply>", text, re.DOTALL)
    skip_m = re.search(r"<skip>(.*?)</skip>", text, re.DOTALL)
    if reply_m and skip_m:
        raise ContractError("reply/skip 태그가 함께 나옴")
    if skip_m:
        return {"skip": True, "reason": skip_m.group(1).strip()}
    if not reply_m:
        raise ContractError("reply/skip 태그를 찾지 못함")
    reply = reply_m.group(1).strip()
    if not reply:
        raise ContractError("reply 가 비어있음")
    return {"skip": False, "reply": reply}
