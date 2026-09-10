-- 주제 제목에 저자를 소급해 붙인다 — '제목' → '제목 - 저자'.
--
-- 매일 자동 생성(auto_create)이 추천 행의 저자를 author 컬럼으로만 넘기고 topic 문자열엔
-- 붙이지 않아, 목록에 '명상록'·'돈의 심리학'처럼 제목만 남았다(2026-09-09 피드백).
-- '제목 - 저자'는 레포가 전제하는 표기다 — backfill_comments._parse_topic 이 " - "로 저자를
-- 떼어 구매 링크 댓글 검색어를 만들고, topics 라우트도 같은 방식으로 추천 행을 매칭한다.
-- 생성 코드는 고쳤고, 이 파일은 이미 쌓인 행을 같은 표기로 맞춘다.
--
-- topic 은 내부 식별용이라 이미 발행된 글·영상의 제목(meta.title)과는 별개다 — 바꿔도
-- 발행물에 영향이 없다.

-- 1) author 가 비었지만 같은 제목의 추천 행에 저자가 남아 있으면 되살린다.
--    (author 컬럼이 생기기 전(0016)에 만들어진 주제가 여기 해당한다.)
UPDATE content_topics
SET author = (
  SELECT r.author FROM content_recommendations r
  WHERE r.owner_sub = content_topics.owner_sub
    AND TRIM(r.title) = TRIM(content_topics.topic)
    AND r.author IS NOT NULL AND TRIM(r.author) <> ''
  ORDER BY r.created_at DESC LIMIT 1
)
WHERE (author IS NULL OR TRIM(author) = '')
  AND EXISTS (
    SELECT 1 FROM content_recommendations r
    WHERE r.owner_sub = content_topics.owner_sub
      AND TRIM(r.title) = TRIM(content_topics.topic)
      AND r.author IS NOT NULL AND TRIM(r.author) <> ''
  );

-- 2) 제목에 저자를 붙인다. 이미 ' - 저자'로 끝나면(직접 등록한 '코스모스 - 칼 세이건' 등)
--    substr 비교에서 걸러져 두 번 붙지 않는다.
UPDATE content_topics
SET topic = TRIM(topic) || ' - ' || TRIM(author)
WHERE author IS NOT NULL AND TRIM(author) <> ''
  AND substr(TRIM(topic), -(length(TRIM(author)) + 3)) <> ' - ' || TRIM(author);

-- 3) 묶음 작업의 topic 을 주제 쪽과 다시 맞춘다(생성 시 같은 문자열을 복사해 두는 구조).
UPDATE content_jobs
SET topic = (SELECT t.topic FROM content_topics t WHERE t.id = content_jobs.topic_id)
WHERE topic_id IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM content_topics t
    WHERE t.id = content_jobs.topic_id AND t.topic <> content_jobs.topic
  );
