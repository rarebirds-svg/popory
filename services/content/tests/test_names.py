from popory_content.names import normalize_names


def test_fixes_author_name_in_title():
    # 실제로 발행됐던 쇼츠 제목. 새퍼 → 섀퍼.
    assert normalize_names("26살에 파산한 남자의 4년 반전 — 보도 새퍼의 돈") == \
        "26살에 파산한 남자의 4년 반전 — 보도 섀퍼의 돈"


def test_fixes_spaceless_form_without_adding_a_space():
    # 붙여 쓴 표기는 붙여 쓴 채로 고친다(원문의 띄어쓰기 습관을 바꾸지 않는다).
    assert normalize_names("보도새퍼의 거위통장") == "보도섀퍼의 거위통장"


def test_leaves_correct_spelling_untouched():
    text = "보도 섀퍼는 거위를 죽이지 말라고 했다"
    assert normalize_names(text) == text


def test_fixes_every_occurrence_across_a_document():
    out = normalize_names('{"title": "보도 새퍼", "tags": ["보도 새퍼", "나폴레옹 힐"]}')
    assert out == '{"title": "보도 섀퍼", "tags": ["보도 섀퍼", "나폴레온 힐"]}'


def test_empty_and_unmatched_text_pass_through():
    assert normalize_names("") == ""
    assert normalize_names(None) is None
    assert normalize_names("고칠 이름이 없는 문장") == "고칠 이름이 없는 문장"
