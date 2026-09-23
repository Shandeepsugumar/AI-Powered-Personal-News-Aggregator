import requests
import time
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"

def send_ingest(source_name, title, content):
    payload = {
        "source_type": "blog",
        "source_name": source_name,
        "source_url": f"https://{source_name.lower()}.com/{uuid.uuid4().hex[:8]}",
        "title": title,
        "content": content
    }
    try:
        resp = requests.post(f"{BASE_URL}/ingest", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Ingest [{source_name}]: Request failed - {e}")
        return {"status": "failed"}
    
    print(f"Ingest [{source_name}]: {data.get('decision', data.get('reason', data.get('status')))}")
    return data

def test_1_exact_duplicate():
    print("\n--- Test 1: Exact Duplicate ---")
    content = "Apple has officially announced the iPhone 18 today in Cupertino. It features a new titanium frame, an A19 Pro chip, and advanced AI capabilities."
    send_ingest("TechCrunch", "iPhone 18", content)
    res = send_ingest("TechCrunch", "iPhone 18", content)
    assert res["status"] == "skipped", "Expected LLM to be skipped on exact duplicate."

def test_2_paraphrase_duplicate():
    print("\n--- Test 2: Paraphrase Duplicate (3 runs) ---")
    passes = 0
    
    # Run 1
    content1 = "The new iPhone 18 was unveiled by Apple at their California event featuring titanium."
    res1 = send_ingest("TheVerge", "Apple unveils new iPhone", content1)
    if res1.get("decision") == "merge": passes += 1
    
    # Run 2
    content2 = "Apple announced the iPhone 18 during a special keynote in Cupertino today."
    res2 = send_ingest("Engadget", "iPhone 18 announced", content2)
    if res2.get("decision") == "merge": passes += 1
        
    # Run 3
    content3 = "At its fall event, Apple revealed the highly anticipated iPhone 18 with A19 Pro."
    res3 = send_ingest("CNET", "Apple's new phone", content3)
    if res3.get("decision") == "merge": passes += 1
        
    print(f"Paraphrase passes: {passes}/3")
    return passes

def test_3_same_topic_different_event():
    print("\n--- Test 3: Same Topic, Different Event (3 runs) ---")
    passes = 0
    
    # Run 1: iPhone
    content1 = "Rumors suggest Apple has already started early development on the iPhone 19 for next year."
    res1 = send_ingest("MacRumors", "iPhone 19 Development", content1)
    if res1.get("decision") in ["separate", "new_group"]: passes += 1
    
    # Run 2: Tesla
    send_ingest("Reuters", "Tesla Spain", "Tesla has officially announced a new Gigafactory in Spain.")
    content2 = "Reports indicate Tesla is looking to build another Gigafactory in Mexico next year."
    res2 = send_ingest("Bloomberg", "Tesla Mexico", content2)
    if res2.get("decision") in ["separate", "new_group"]: passes += 1
    
    # Run 3: Google
    send_ingest("TechCrunch", "Pixel 9", "Google just launched the Pixel 9 at its hardware event.")
    content3 = "Leaks of the Google Pixel 10 show a radical new design."
    res3 = send_ingest("9to5Google", "Pixel 10 leaks", content3)
    if res3.get("decision") in ["separate", "new_group"]: passes += 1

    print(f"Different event passes: {passes}/3")
    return passes

def test_4_conflicting_facts():
    print("\n--- Test 4: Conflicting Facts (3 runs) ---")
    passes = 0
    
    # Run 1: Price conflict
    send_ingest("Wired", "Galaxy S25 Price", "The new Samsung Galaxy S25 will be priced at $799.")
    res1 = send_ingest("Engadget", "S25 Launch", "Samsung is launching the Galaxy S25 starting at $899.")
    if res1.get("decision") == "merge": passes += 1
    
    # Run 2: Battery conflict
    send_ingest("Gizmodo", "Oppo Find X", "The Oppo Find X has a 4000mAh battery.")
    res2 = send_ingest("TechRadar", "Oppo specs", "The battery on the new Oppo Find X is 4500mAh.")
    if res2.get("decision") == "merge": passes += 1
    
    # Run 3: Release date conflict
    send_ingest("CNBC", "PS6 Release", "Sony will release the PlayStation 6 in November 2027.")
    res3 = send_ingest("IGN", "PS6 Date", "The PlayStation 6 is slated for a March 2028 release.")
    if res3.get("decision") == "merge": passes += 1
    
    print(f"Conflicting facts passes: {passes}/3")
    return passes

def test_5_cross_batch_merge():
    print("\n--- Test 5: Cross-Batch Merge ---")
    content_a = "Microsoft has announced a new AI research center in London."
    send_ingest("Reuters", "MSFT London", content_a)
    time.sleep(2)
    content_b = "A new Microsoft AI hub will be built in the UK capital."
    res = send_ingest("Bloomberg", "Microsoft UK Hub", content_b)
    assert res["decision"] == "merge", "Expected cross-batch to merge."

def test_6_edition_counter():
    print("\n--- Test 6: Edition Counter ---")
    r1 = requests.get(f"{BASE_URL}/newspaper?user_id=test_user")
    ed1 = r1.json()["editionNumber"]
    
    r2 = requests.get(f"{BASE_URL}/newspaper?user_id=test_user")
    ed2 = r2.json()["editionNumber"]
    
    print(f"Edition 1: {ed1}, Edition 2: {ed2}")
    assert ed2 > ed1, "Expected editionNumber to increment on consecutive calls."

def test_7_importance_ranking():
    print("\n--- Test 7: Importance Ranking ---")
    r = requests.get(f"{BASE_URL}/newspaper?user_id=test_user")
    stories = r.json().get("stories", [])
    
    for s in stories:
        src_count = len(s["sources"])
        print(f"Story: {s['headline'][:30]}... Sources: {src_count}, Importance: {s['importance']}")
        if src_count >= 2:
            assert s['importance'] in ["lead", "major"], "Multiple sources should be lead/major."
        else:
            assert s['importance'] in ["minor", "lead", "major"], "Single source could be minor."

if __name__ == "__main__":
    print("Waiting for server to be ready...")
    time.sleep(2)
    test_1_exact_duplicate()
    t2 = test_2_paraphrase_duplicate()
    t3 = test_3_same_topic_different_event()
    t4 = test_4_conflicting_facts()
    test_5_cross_batch_merge()
    test_6_edition_counter()
    test_7_importance_ranking()
    print(f"\nSemantic Tests Summary: Paraphrase={t2}/3, DiffEvent={t3}/3, Conflict={t4}/3")
    print("\nAll automated checks completed!")
