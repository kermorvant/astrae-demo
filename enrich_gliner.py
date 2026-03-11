import json
import argparse
from tqdm import tqdm
try:
    from gliner import GLiNER
except ImportError:
    print("GLiNER not found. Please install with: pip install gliner")
    exit(1)

def main():
    parser = argparse.ArgumentParser(description="Enrich JSON data with GLiNER NER")
    parser.add_argument("--input", type=str, default="data_objects.json", help="Input JSON file")
    parser.add_argument("--output", type=str, default="data_objects_enriched.json", help="Output JSON file")
    args = parser.parse_args()

    print("Loading GLiNER model...")
    # 'urchade/gliner_mediumv2.1' is a solid default for generic NER
    model = GLiNER.from_pretrained("urchade/gliner_mediumv2.1")

    labels = ["person", "artwork", "organisation", "date", "location", "event"]
    
    ENTITY_TYPE_TO_LEVEL = {
        "person": 7,
        "artist": 7,
        "mythological_figure": 7,
        "character": 7,
        "deity": 7,
        "organisation": 7,
        "organization": 7,
        "artwork": 7,
        "place": 8,
        "location": 8,
        "event": 8
    }

    print(f"Loading data from {args.input}...")
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])
    print(f"Total elements loaded: {len(elements)}")

    paragraphs_to_process = [el for el in elements if el.get("type") == "paragraph"]
    # Limit to 50 for testing
    paragraphs_to_process = paragraphs_to_process[:1000]
    
    print(f"Processing {len(paragraphs_to_process)} paragraph elements...")
    nb_entities = 0
    for el in tqdm(paragraphs_to_process):
        text = el.get("text", "")
            
        if not text:
            continue
            
        # Pre-process text to remove hyphenation (e.g., "tech- nique" -> "technique")
        # Removing a hyphen followed by any whitespace characters.
        import re
        text = re.sub(r'-\s+', '', text)
        el["text"] = text
            
        # Predict entities
        entities = model.predict_entities(text, labels)
        
        if "concepts" not in el:
            el["concepts"] = []
        if "concept_mentions" not in el:
            el["concept_mentions"] = []
            
        import hashlib
            
        for ent in entities:
            # GLiNER returns dicts with 'start', 'end', 'label', 'text'
            offset = ent.get("start", 0)
            length = ent.get("end", 0) - offset
            
            text_val = ent["text"]
            lbl_type = ent["label"].lower()
            cid = f"entity_{hashlib.md5(text_val.encode()).hexdigest()[:8]}"
            
            p_level = ENTITY_TYPE_TO_LEVEL.get(lbl_type, 7)
            
            if not any(c["id"] == cid for c in el["concepts"]):
                el["concepts"].append({
                    "id": cid,
                    "label": text_val,
                    "vocabulary": "entity",
                    "pyramid_level": p_level,
                    "category": lbl_type,
                    "source": { "method": "ai", "agent": "gliner" }
                })
            
            el["concept_mentions"].append({
                "concept_id": cid,
                "element_id": el.get("id"),
                "offset": offset,
                "length": length,
                "source": { "method": "ai", "agent": "gliner" }
            })
            nb_entities += 1

    print(f"Found {nb_entities}")
    print(f"Saving enriched data to {args.output}...")
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print("Done!")

if __name__ == "__main__":
    main()
