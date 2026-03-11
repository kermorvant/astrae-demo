import streamlit as st
import streamlit.components.v1 as components
import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Source:
    method: str               # "manual", "ai", "ocr", "import"
    agent: Optional[str] = None   # user id, model name (e.g. "gliner-base")
    confidence: Optional[float] = None

@dataclass
class IIIFRegion:
    x: int
    y: int
    width: int
    height: int
    rotation_angle: int
    source: Optional[Source] = None

@dataclass
class Metadata:
    name: str
    value: str
    type: str
    source: Optional[Source] = None

@dataclass
class Concept:
    id: str
    label: str
    vocabulary: str
    pyramid_level: int
    category: Optional[str] = None
    external_id: Optional[str] = None
    source: Optional[Source] = None

@dataclass
class ConceptMention:
    concept_id: str
    element_id: str
    offset: Optional[int] = None
    length: Optional[int] = None
    source: Optional[Source] = None

@dataclass
class Document:
    id: str
    title: str
    creator: str
    date: str
    metadata: List[Metadata] = field(default_factory=list)

PYRAMID_LEVELS = {
    1: "type_technique",
    2: "global_distribution",
    3: "local_structure",
    4: "global_composition",
    5: "generic_object",
    6: "generic_scene",
    7: "specific_object",
    8: "specific_scene",
    9: "abstract_object",
    10: "abstract_scene"
}

@dataclass
class View:
    id: str
    document_id: str
    iiif_base: str
    region: IIIFRegion
    name: str

@dataclass
class Element:
    id: str
    type: str

    text: str = ""
    text_source: Optional[Source] = None

    description: str = ""
    description_source: Optional[Source] = None

    view_id: str = None
    iiif_base: str = None

    region: Optional[IIIFRegion] = None

    metadata: List[Metadata] = field(default_factory=list)
    
    concepts: List[Concept] = field(default_factory=list)
    concept_mentions: List[ConceptMention] = field(default_factory=list)

    view: Optional[View] = None
    document: Optional[Document] = None

@st.cache_data
def load_data(filepath: str):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        docs = {d['id']: Document(**d) for d in data.get('documents', [])}
        
        views = {}
        for v in data.get('views', []):
            if v.get('region'):
                region_data = v['region']
                if 'source' in region_data and region_data['source']:
                    region_data['source'] = Source(**region_data['source'])
                v['region'] = IIIFRegion(**region_data)
            else:
                v['region'] = None
            views[v['id']] = View(**v)
            
        elements = []
        for e in data.get('elements', []):
            e_type = e.get('type')
            
            region = None
            if e.get('region'):
                region_data = e['region']
                if 'source' in region_data and region_data['source']:
                    region_data['source'] = Source(**region_data['source'])
                region = IIIFRegion(**region_data)
                
            metas = []
            for m in e.get('metadata', []):
                if 'source' in m and m['source']:
                    m['source'] = Source(**m['source'])
                metas.append(Metadata(**m))
                
            concepts = []
            for c in e.get('concepts', []):
                if 'source' in c and c['source']:
                    c['source'] = Source(**c['source'])
                concepts.append(Concept(**c))
                
            concept_mentions = []
            for cm in e.get('concept_mentions', []):
                if 'source' in cm and cm['source']:
                    cm['source'] = Source(**cm['source'])
                concept_mentions.append(ConceptMention(**cm))
                
            text_source = None
            if e.get('text_source'):
                text_source = Source(**e['text_source'])
                
            desc_source = None
            if e.get('description_source'):
                desc_source = Source(**e['description_source'])
            
            el = Element(
                id=e['id'],
                type=e_type,
                text=e.get('text', ''),
                text_source=text_source,
                description=e.get('description', ''),
                description_source=desc_source,
                view_id=e.get('view_id'),
                iiif_base=e.get('iiif_base'),
                region=region,
                metadata=metas,
                concepts=concepts,
                concept_mentions=concept_mentions
            )
            
            if el.view_id and el.view_id in views:
                el.view = views[el.view_id]
                if el.view.document_id and el.view.document_id in docs:
                    el.document = docs[el.view.document_id]
            
            elements.append(el)
            
        return elements
    except FileNotFoundError:
        st.error(f"File {filepath} not found.")
        return []

def get_snippet_url(el: Element) -> str:
    # If the element itself has iiif_base (like ArtWork), use it, otherwise use its view
    iiif = el.iiif_base
    if not iiif and el.view:
        iiif = el.view.iiif_base
        
    if not iiif:
        return ""
        
    r = el.region
    if r and r.width > 0 and r.height > 0:
        return f"{iiif}/{r.x},{r.y},{r.width},{r.height}/full/0/default.jpg"
    return f"{iiif}/full/300,/0/default.jpg"

def get_openseadragon_html(iiif_base: str, region: IIIFRegion) -> str:
    highlight_script = ""
    if region and region.width > 0 and region.height > 0:
        highlight_script = f"""
            viewer.addHandler("open", function() {{
                var rect = new OpenSeadragon.Rect({region.x}, {region.y}, {region.width}, {region.height});
                var viewportRect = viewer.viewport.imageToViewportRectangle(rect);
                
                var elt = document.createElement("div");
                elt.className = "highlight-box";
                
                viewer.addOverlay({{
                    element: elt,
                    location: viewportRect
                }});
                
                // Fit bounds slightly padded
                var pad = Math.max(viewportRect.width, viewportRect.height) * 0.5;
                var paddedRect = new OpenSeadragon.Rect(
                    viewportRect.x - pad/2,
                    viewportRect.y - pad/2,
                    viewportRect.width + pad,
                    viewportRect.height + pad
                );
                viewer.viewport.fitBounds(paddedRect);
            }});
        """

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/openseadragon.min.js"></script>
        <style>
            html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
            #openseadragon1 {{ width: 100%; height: 600px; }}
            .highlight-box {{ 
                border: 3px solid red; 
                background-color: rgba(255, 0, 0, 0.2); 
                pointer-events: none; 
            }}
        </style>
    </head>
    <body>
        <div id="openseadragon1"></div>
        <script>
            var viewer = OpenSeadragon({{
                id: "openseadragon1",
                prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
                tileSources: "{iiif_base}/info.json",
                showNavigationControl: true
            }});
            {highlight_script}
        </script>
    </body>
    </html>
    """
    return html_code

def render_source_badge(source: Optional[Source]) -> str:
    if not source:
        return ""
    agent_str = f"/{source.agent}" if source.agent else ""
    full_info = f"{source.method}{agent_str}"
    
    icon = "👤" if source.method == "manual" else "✨"
    
    return f"<span title='{full_info}' style='cursor: help; margin-left: 6px; font-size: 1.1em;'>{icon}</span>"

def show_detail_page(el: Element, search_query: str = ""):
    st.button("← Back to Search", on_click=lambda: st.session_state.pop('selected_element'))
    
    st.header(f"Details: {el.type.capitalize()} ({el.id})")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Context Image")
        # Find base IIIF
        iiif = el.iiif_base
        if not iiif and el.view:
            iiif = el.view.iiif_base
            
        if iiif:
            st.markdown(f"*Interactive IIIF Context Viewer*{render_source_badge(el.region.source if el.region else None)}", unsafe_allow_html=True)
            region_to_draw = None if el.type == 'painting' else el.region
            html_code = get_openseadragon_html(iiif, region_to_draw)
            components.html(html_code, height=620)
        else:
            st.warning("No context image available.")
            
    with col2:
        st.subheader("Source Information")
        if el.document:
            st.markdown(f"**Document Title:** {el.document.title}")
            st.markdown(f"**Creator:** {el.document.creator}")
            st.markdown(f"**Date:** {el.document.date}")
            
            if el.document.metadata:
                with st.expander("Document Metadata"):
                    for m in el.document.metadata:
                        st.markdown(f"  - **{m.name}**: {m.value} {render_source_badge(m.source)}", unsafe_allow_html=True)
        else:
            st.markdown("*No document information linked.*")
            
        if el.view:
            st.markdown(f"**View Name:** {el.view.name}")
            
        if el.metadata:
            st.markdown("**Element Metadata:**")
            for m in el.metadata:
                st.markdown(f"- **{m.name}**: {m.value} {render_source_badge(m.source)}", unsafe_allow_html=True)
            
        st.markdown("---")
        st.subheader("Element Details")
        
        main_text = el.text if el.type == 'paragraph' else el.description
        if main_text:
            text_to_display = main_text
            
            if el.concept_mentions:
                # Filter mentions that have offsets (to highlight in text)
                ent_mentions = [cm for cm in el.concept_mentions if cm.offset is not None]
                if ent_mentions:
                    # Collect unique sources from these mentions
                    sources = []
                    for cm in ent_mentions:
                        if cm.source and cm.source not in sources:
                            sources.append(cm.source)
                    badges = "".join([render_source_badge(s) for s in sources])
                    st.markdown(f"*{len(ent_mentions)} Concept Mentions in Text* {badges}", unsafe_allow_html=True)
                    
                    # Need to replace from back to front so we don't mess up offsets
                    sorted_mentions = sorted(ent_mentions, key=lambda x: x.offset, reverse=True)
                    for ent in sorted_mentions:
                        concept = next((c for c in el.concepts if c.id == ent.concept_id), None)
                        if not concept:
                            continue
                        
                        start = ent.offset
                        end = start + ent.length
                        
                        if start >= 0 and end <= len(text_to_display):
                            # Determine color and short code based on type
                            color = "#e2e8f0"  # generic gray
                            short_code = "CON"
                            if concept.vocabulary == "entity":
                                short_code = "ENT"
                                color = "#fed7aa" # default orangeish
                                if getattr(concept, 'category', None):
                                    cat = concept.category.lower()
                                    if cat == "person":
                                        short_code = "PER"
                                        color = "#fed7aa" 
                                    elif cat in ["location", "place"]:
                                        short_code = "LOC"
                                        color = "#bbf7d0" 
                                    elif cat == "date":
                                        short_code = "DAT"
                                        color = "#bfdbfe" 
                                    elif cat in ["organisation", "organization", "institution"]:
                                        short_code = "ORG"
                                        color = "#fbcfe8" 
                                    elif cat == "artwork":
                                        short_code = "ART"
                                        color = "#fef08a" 
                                    elif cat in ["event", "exhibition"]:
                                        short_code = "EVE"
                                        color = "#e9d5ff" 
                                    else:
                                        short_code = cat[:3].upper()
                            elif concept.vocabulary == "iconclass":
                                color = "#fef08a" # yellowish
                                short_code = "ICO"
                                
                            original_substr = text_to_display[start:end]
                            highlighted = f"<mark style='background-color: {color}; color: #000; padding: 2px 4px; border-radius: 4px; line-height: 2;'>{original_substr} <span style='font-size: 0.7em; font-weight: bold; opacity: 0.7;'>{short_code}</span></mark>"
                            
                            text_to_display = text_to_display[:start] + highlighted + text_to_display[end:]
                        
            # Highlight the search term if present
            if search_query:
                escaped_query = re.escape(search_query.strip())
                if escaped_query:
                    # Case-insensitive replacement, wrapping matched terms in neon yellow
                    text_to_display = re.sub(
                        f"({escaped_query})",
                        r"<mark style='background-color: #ffeb3b; color: #000; padding: 0 4px; border-radius: 3px;'>\1</mark>",
                        text_to_display,
                        flags=re.IGNORECASE
                    )
                        
            src = el.text_source if el.type == 'paragraph' else el.description_source
            st.markdown(f"**Text / Description:** {render_source_badge(src)}\n\n{text_to_display}", unsafe_allow_html=True)
            
        if el.concepts:
            st.markdown("**Concepts:**")
            
            # Group concepts by their pyramid level
            from collections import defaultdict
            grouped_concepts = defaultdict(list)
            for c in el.concepts:
                grouped_concepts[c.pyramid_level].append(c)
                
            sorted_levels = sorted(grouped_concepts.keys())
            for level in sorted_levels:
                level_name = PYRAMID_LEVELS.get(level, "unknown")
                
                items = []
                for c in grouped_concepts[level]:
                    badge = render_source_badge(c.source)
                    if c.vocabulary == 'iconclass':
                        items.append(f" **[{c.external_id}]** {c.label.capitalize()} {badge}")
                    elif c.vocabulary == 'entity':
                        cat_str = f" ({c.category})" if getattr(c, 'category', None) else ""
                        items.append(f"{c.label}{cat_str} {badge}")
                    else:
                        items.append(f"📌 {c.label} {badge}")
                
                st.markdown(f"**Level {level} ({level_name.replace('_', ' ').title()})** &nbsp;&nbsp; " + " &nbsp;|&nbsp; ".join(items), unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Data Search Demo", layout="wide")
    
    elements = load_data('data_objects_enriched.json')
    if not elements:
        return
        
    # Sidebar filters
    st.sidebar.header("Search Filters")
    search_query = st.sidebar.text_input("Search text (case-insensitive):", "")
    
    if 'selected_element' in st.session_state:
        show_detail_page(st.session_state['selected_element'], search_query)
        return
    type_options = list(set(e.type for e in elements))
    selected_types = st.sidebar.multiselect("Filter by type:", options=type_options, default=type_options)
    
    if 'page_num' not in st.session_state:
        st.session_state.page_num = 0

    numeric_meta = {}
    date_meta = {}
    
    for e in elements:
        if e.metadata:
            for m in e.metadata:
                if m.type == 'numeric' and m.value is not None:
                    try:
                        val = float(m.value)
                        if m.name not in numeric_meta:
                            numeric_meta[m.name] = {'min': val, 'max': val}
                        else:
                            numeric_meta[m.name]['min'] = min(numeric_meta[m.name]['min'], val)
                            numeric_meta[m.name]['max'] = max(numeric_meta[m.name]['max'], val)
                    except ValueError:
                        pass
                        
                elif m.type == 'date' and m.value is not None:
                    try:
                        val = datetime.strptime(str(m.value).split('T')[0], '%Y-%m-%d').date()
                        if m.name not in date_meta:
                            date_meta[m.name] = {'min': val, 'max': val}
                        else:
                            date_meta[m.name]['min'] = min(date_meta[m.name]['min'], val)
                            date_meta[m.name]['max'] = max(date_meta[m.name]['max'], val)
                    except ValueError:
                        pass
    
    st.sidebar.markdown("---")
    st.sidebar.header("Metadata Filters")
    
    active_filters = {'numeric': {}, 'date': {}}
    
    for name, bounds in numeric_meta.items():
        if bounds['min'] < bounds['max']: 
            with st.sidebar.expander(f"Filter by {name}"):
                selected_range = st.slider(
                    f"{name}", 
                    min_value=float(bounds['min']), 
                    max_value=float(bounds['max']), 
                    value=(float(bounds['min']), float(bounds['max'])),
                    key=f"slider_{name}"
                )
                if selected_range != (bounds['min'], bounds['max']):
                    active_filters['numeric'][name] = selected_range

    for name, bounds in date_meta.items():
        if bounds['min'] < bounds['max']:
            with st.sidebar.expander(f"Filter by {name}"):
                start_date = st.date_input(f"{name} (Start)", value=bounds['min'], min_value=bounds['min'], max_value=bounds['max'], key=f"ds_{name}")
                end_date = st.date_input(f"{name} (End)", value=bounds['max'], min_value=bounds['min'], max_value=bounds['max'], key=f"de_{name}")
                if start_date > bounds['min'] or end_date < bounds['max']:
                    active_filters['date'][name] = (start_date, end_date)

    current_state = (search_query, selected_types, list(active_filters['numeric'].items()), list(active_filters['date'].items()))
    if 'last_query' not in st.session_state or st.session_state.last_query != current_state:
        st.session_state.page_num = 0
        st.session_state.last_query = current_state

    results = elements
    
    if selected_types:
        results = [e for e in results if e.type in selected_types]
        
    if search_query:
        query_lower = search_query.lower()
        new_results = []
        for e in results:
            main_text = e.text if e.type == 'paragraph' else e.description
            match_text = query_lower in (main_text or "").lower()
            match_meta = False
            match_entity = False
            
            if e.metadata:
                for m in e.metadata:
                    if m.type == 'text' and m.value:
                        if query_lower in str(m.value).lower():
                            match_meta = True
                            
            if e.concept_mentions:
                for cm in e.concept_mentions:
                    concept = next((c for c in e.concepts if c.id == cm.concept_id), None)
                    if concept and concept.label and query_lower in concept.label.lower():
                        match_entity = True
                        break
            
            if match_text or match_meta or match_entity:
                e._match_text = match_text
                e._match_meta = match_meta
                e._match_entity = match_entity
                new_results.append(e)
        results = new_results

    if active_filters['numeric'] or active_filters['date']:
        filtered_results = []
        for e in results:
            keep = True
            if not e.metadata:
                keep = False
            else:
                meta_dict = {m.name: m for m in e.metadata}
                
                for name, (min_v, max_v) in active_filters['numeric'].items():
                    if name not in meta_dict:
                        keep = False
                        break
                    try:
                        val = float(meta_dict[name].value)
                        if not (min_v <= val <= max_v):
                            keep = False
                            break
                    except (ValueError, TypeError):
                        keep = False
                        break
                
                if not keep:
                    continue
                    
                for name, (start_d, end_d) in active_filters['date'].items():
                    if name not in meta_dict:
                        keep = False
                        break
                    try:
                        val = datetime.strptime(str(meta_dict[name].value).split('T')[0], '%Y-%m-%d').date()
                        if not (start_d <= val <= end_d):
                            keep = False
                            break
                    except (ValueError, TypeError):
                        keep = False
                        break
            
            if keep:
                filtered_results.append(e)
        results = filtered_results
        
    total_results = len(results)
    
    items_per_page = 50
    start_idx = st.session_state.page_num * items_per_page
    end_idx = start_idx + items_per_page
    paginated_results = results[start_idx:end_idx]
        
    if total_results > 0:
        st.subheader(f"Found {total_results} results (showing {start_idx + 1}-{min(end_idx, total_results)})")
    else:
        st.subheader(f"Found 0 results")
    
    num_columns = 5
    for i in range(0, len(paginated_results), num_columns):
        cols = st.columns(num_columns)
        for j, col in enumerate(cols):
            if i + j < len(paginated_results):
                e = paginated_results[i + j]
                with col:
                    with st.container(border=True):
                        type_color = "#1f77b4" if e.type == "paragraph" else "#ff7f0e" if e.type == "illustration" else "#2ca02c"
                        st.markdown(f"<span style='background-color: {type_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em;'>{e.type.upper()}</span> <a href='https://arkindex.teklia.com/element/{e.id}' target='_blank' style='text-decoration:none; font-size: 0.8em;'>🔗</a>", unsafe_allow_html=True)
                        
                        has_search = bool(search_query.strip())
                        match_text = getattr(e, '_match_text', False)
                        match_meta = getattr(e, '_match_meta', False)
                        match_entity = getattr(e, '_match_entity', False)
                        
                        if e.type in ['illustration', 'painting']:
                            match_labels = []
                            if has_search:
                                if match_text:
                                    match_labels.append("content")
                                if match_meta:
                                    match_labels.append("metadata")
                                if match_entity:
                                    match_labels.append("entity")
                            else:
                                match_labels.append("content")
                                
                            if not match_labels:
                                match_labels.append("content")
                                
                            st.markdown(f"**Matching : {', '.join(match_labels)}**")
                        else:
                            match_labels = []
                            if has_search:
                                if match_text:
                                    match_labels.append("text")
                                if match_meta:
                                    match_labels.append("metadata")
                                if match_entity:
                                    match_labels.append("entity")
                            else:
                                match_labels.append("text")
                                
                            if not match_labels:
                                match_labels.append("text")
                            
                            st.markdown(f"**Matching : {', '.join(match_labels)}**")
                                
                            main_text = e.text if e.type == 'paragraph' else e.description
                            highlighted_text = main_text
                            if has_search and match_text and main_text:
                                match = re.search(re.escape(search_query.strip()), main_text, re.IGNORECASE)
                                if match:
                                    start_idx = match.start()
                                    end_idx = match.end()
                                    
                                    prefix = main_text[:start_idx]
                                    suffix = main_text[end_idx:]
                                    
                                    prefix_words = prefix.split()
                                    suffix_words = suffix.split()
                                    
                                    truncated_prefix = " ".join(prefix_words[-10:]) if len(prefix_words) > 10 else prefix
                                    truncated_suffix = " ".join(suffix_words[:10]) if len(suffix_words) > 10 else suffix
                                    
                                    if len(prefix_words) > 10:
                                        truncated_prefix = "... " + truncated_prefix
                                    if len(suffix_words) > 10:
                                        truncated_suffix = truncated_suffix + " ..."
                                        
                                    highlighted_text = truncated_prefix + main_text[start_idx:end_idx] + truncated_suffix

                                escaped_query = re.escape(search_query.strip())
                                highlighted_text = re.sub(
                                    f"({escaped_query})",
                                    r"<mark style='background-color: #ffeb3b; color: #000; padding: 0 4px; border-radius: 3px;'>\1</mark>",
                                    highlighted_text,
                                    flags=re.IGNORECASE
                                )
                                
                            st.markdown(f"{highlighted_text}", unsafe_allow_html=True)
                        
                        snippet_url = get_snippet_url(e)
                        if snippet_url:
                            st.markdown(f"[![Snippet Image]({snippet_url})]({snippet_url})")
                        
                        if st.button("View Details", key=f"btn_det_{e.id}"):
                            st.session_state['selected_element'] = e
                            st.rerun()

    if total_results > items_per_page:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("Previous Page", disabled=(st.session_state.page_num == 0)):
                st.session_state.page_num -= 1
                st.rerun()
        with col3:
            if st.button("Next Page", disabled=(end_idx >= total_results)):
                st.session_state.page_num += 1
                st.rerun()

if __name__ == "__main__":
    main()
