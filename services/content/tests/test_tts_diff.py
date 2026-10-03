# tools/tts_diff.py — '바뀐 문장만' 전/후로 보여 주는 도구의 핵심 로직.
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from popory_content.tts import spoken_text
from popory_content.video import _split_sentences

_spec = importlib.util.spec_from_file_location("tts_diff", Path(__file__).resolve().parents[1] / "tools" / "tts_diff.py")
tts_diff = importlib.util.module_from_spec(_spec)
sys.modules["tts_diff"] = tts_diff
_spec.loader.exec_module(tts_diff)


def test_narration_lines_skip_scene_titles_and_blanks():
    text = "[장면 1]\n첫 문장입니다.\n\n[장면 2]\n둘째 문장입니다."
    assert tts_diff.narration_lines(text) == ["첫 문장입니다.", "둘째 문장입니다."]


def test_only_changed_sentences_are_reported():
    old = lambda s: s.replace("3명", "삼명")        # 가짜 '전': 모든 숫자를 한자어로 읽던 때를 흉내
    texts = [("a.txt", "[장면]\n3명이 왔다. 바뀌지 않는 문장이다.")]
    total, changed = tts_diff.changed_sentences(texts, _split_sentences, old, spoken_text)
    assert total == 2
    assert [c["text"] for c in changed] == ["3명이 왔다."]
    assert changed[0]["after"] == "세 명이 왔다."


def test_load_tts_at_returns_an_isolated_module_from_git():
    """git 의 tts.py 를 별도 모듈로 불러온다 — 작업 트리의 실제 모듈과 섞이지 않는다(항상 있는 HEAD 로 검증)."""
    from popory_content import tts as live
    mod = tts_diff.load_tts_at("HEAD")
    assert mod is not live and callable(mod.spoken_text)
    assert mod.spoken_text("안녕하세요.") == live.spoken_text("안녕하세요.")


def _has_rev(rev: str) -> bool:
    import subprocess
    return subprocess.run(["git", "-C", str(tts_diff.ROOT), "cat-file", "-e", rev],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not _has_rev(tts_diff.DEFAULT_BEFORE_REV),
                    reason="shallow clone(CI 의 기본 checkout) 에는 #67 직전 커밋이 없다 — 이력이 있는 clone 에서만 의미가 있다")
def test_default_before_rev_reads_digits_as_sino():
    """'전' 은 기억이 아니라 git 이력의 옛 tts.py 를 그대로 돌린 결과여야 한다."""
    old = tts_diff.load_tts_at(tts_diff.DEFAULT_BEFORE_REV)
    assert old.spoken_text("1권, 3가지") == "일권, 삼가지"
    assert spoken_text("1권, 3가지") == "일권, 세 가지"      # 권은 권차라 한자어 유지, 가지는 고유어


def test_reads_dirs_files_and_json(tmp_path):
    (tmp_path / "a.txt").write_text("첫 번째 대본 3가지", encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(["JSON 대본 1권", {"draft": "초안 2권"}], ensure_ascii=False), encoding="utf-8")
    got = dict(tts_diff.read_texts([str(tmp_path)]))
    assert set(got) == {"a.txt", "b.json#1", "b.json#2"}
    assert got["b.json#2"] == "초안 2권"


def test_missing_path_and_empty_folder_exit_with_a_one_line_hint_not_a_traceback(tmp_path, capsys):
    assert tts_diff.main([str(tmp_path / "없는폴더")]) == 2
    assert "경로가 없다" in capsys.readouterr().err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert tts_diff.main([str(empty)]) == 2
    assert "읽을 대본이 없다" in capsys.readouterr().err


def test_counts_per_file_and_ignores_non_script_json_objects(tmp_path):
    """'34건을 줬는데 77건' 같은 불일치: 파일별 건수를 보여 주고, 대본이 아닌 JSON 객체·빈 파일은 세지 않는다."""
    (tmp_path / "scripts.json").write_text(json.dumps([{"draft": f"대본 {i}"} for i in range(3)], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps([{"title": "대본 아님", "id": 1}, {"id": 2}]), encoding="utf-8")   # 메타데이터
    (tmp_path / "empty.txt").write_text("  \n", encoding="utf-8")
    sub = tmp_path / "old"
    sub.mkdir()
    (sub / "notes.md").write_text("옛 메모", encoding="utf-8")
    texts = tts_diff.read_texts([str(tmp_path)])
    counts = tts_diff.count_by_file(texts)
    assert counts == {"scripts.json": 3, "old/notes.md": 1}       # meta.json·empty.txt 는 0건, 하위 폴더는 경로로 구분


def test_out_option_writes_full_report_and_prints_summary_only(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("3가지 원칙을 말합니다.", encoding="utf-8")
    out = tmp_path / "result.txt"
    assert tts_diff.main([str(tmp_path / "a.txt"), "-o", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "전체 결과 →" in printed and "원문:" not in printed          # 터미널엔 요약만
    assert "[a.txt]" not in printed                                      # 바뀐 문장의 머리글이 요약에 새지 않는다
    body = out.read_text(encoding="utf-8")
    assert "원문: 3가지 원칙을 말합니다." in body and "후:   세 가지 원칙을 말합니다." in body


def test_result_file_inside_the_scanned_folder_is_not_read_back_as_input(tmp_path):
    """회귀: -o 로 결과를 대본 폴더 안에 저장하면 다음 실행이 그 결과를 대본으로 다시 읽어 건수가 부풀었다."""
    (tmp_path / "a.txt").write_text("3가지 원칙을 말합니다.", encoding="utf-8")
    out = tmp_path / "result.txt"
    assert tts_diff.main([str(tmp_path), "-o", str(out)]) == 0
    assert tts_diff.main([str(tmp_path), "-o", str(out)]) == 0          # 두 번째 실행이 첫 결과를 읽으면 안 된다
    texts = tts_diff.read_texts([str(tmp_path)], exclude={out})
    assert tts_diff.count_by_file(texts) == {"a.txt": 1}
    assert "읽은 파일 1개 · 대본 1건" in out.read_text(encoding="utf-8")
