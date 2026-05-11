from __future__ import annotations

from marius.storage.watch_store import WatchStore


def test_watch_store_add_list_remove(tmp_path):
    store = WatchStore(tmp_path)

    topic = store.add(
        title="Marius news",
        query="Marius project updates",
        tags=["marius"],
        settings={"notify": "new"},
    )
    listed = store.list_topics()
    removed = store.remove(topic.id)

    assert topic.id == "marius-news"
    assert listed[0].query == "Marius project updates"
    assert listed[0].tags == ["marius"]
    assert listed[0].settings["notify"] == "new"
    assert removed is True
    assert store.list_topics() == []


def test_watch_store_unique_ids(tmp_path):
    store = WatchStore(tmp_path)

    first = store.add(title="Same", query="one")
    second = store.add(title="Same", query="two")

    assert first.id == "same"
    assert second.id == "same-2"


def test_watch_store_save_report_updates_last_run(tmp_path):
    store = WatchStore(tmp_path)
    topic = store.add(title="AI", query="AI news")

    report = store.save_report(topic, [{"title": "A", "url": "https://example.com"}])
    reloaded = store.get(topic.id)
    reports = store.list_reports()

    assert report.topic_id == topic.id
    assert reloaded is not None
    assert reloaded.last_run_at
    assert reports[0].results[0]["title"] == "A"
    assert reports[0].metadata["result_count"] == 1


def test_watch_store_deduplicates_report_urls(tmp_path):
    store = WatchStore(tmp_path)
    topic = store.add(title="AI", query="AI news")
    store.save_report(topic, [{"title": "A", "url": "https://example.com/a"}])

    report = store.save_report(
        topic,
        [
            {"title": "A again", "url": "https://example.com/a"},
            {"title": "B", "url": "https://example.com/b"},
        ],
    )

    assert [item["title"] for item in report.results] == ["B"]
    assert "duplicate" in report.summary
