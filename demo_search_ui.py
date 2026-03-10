import streamlit as st
import streamlit.components.v1 as components
import json
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class IIIFRegion:
    x: int
    y: int
    width: int
    height: int
    rotation_angle: int

@dataclass
class Metadata:
    name: str
    value: str
    type: str

@dataclass
class Document:
    id: str
    title: str
    creator: str
    date: str
    metadata: List[Metadata] = field(default_factory=list)

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
    description: str = ""
    view_id: str = None
    iiif_base: str = None
    region: IIIFRegion = None
    metadata: List[Metadata] = field(default_factory=list)
    
    view: View = None
    document: Document = None

@st.cache_data
def load_data(filepath: str):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        docs = {d['id']: Document(**d) for d in data.get('documents', [])}
        
        views = {}
        for v in data.get('views', []):
            v['region'] = IIIFRegion(**v['region']) if v.get('region') else None
            views[v['id']] = View(**v)
            
        elements = []
        for e in data.get('elements', []):
            e_type = e.get('type')
            region = IIIFRegion(**e['region']) if e.get('region') else None
            metas = [Metadata(**m) for m in e.get('metadata', [])]
            
            el = Element(
                id=e['id'],
                type=e_type,
                text=e.get('text', ''),
                description=e.get('description', ''),
                view_id=e.get('view_id'),
                iiif_base=e.get('iiif_base'),
                region=region,
                metadata=metas
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

def show_detail_page(el: Element):
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
            st.markdown("*Interactive IIIF Context Viewer*")
            html_code = get_openseadragon_html(iiif, el.region)
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
                        st.markdown(f"  - **{m.name}**: {m.value}")
        else:
            st.markdown("*No document information linked.*")
            
        if el.view:
            st.markdown(f"**View Name:** {el.view.name}")
            
        st.markdown("---")
        st.subheader("Element Details")
        
        main_text = el.text if el.type == 'paragraph' else el.description
        if main_text:
            st.markdown(f"**Text / Description:**\n\n{main_text}")
            
        if el.metadata:
            st.markdown("**Element Metadata:**")
            for m in el.metadata:
                st.markdown(f"- **{m.name}**: {m.value}")

def main():
    st.set_page_config(page_title="Data Search Demo", layout="wide")
    
    elements = load_data('data_objects.json')
    if not elements:
        return
        
    if 'selected_element' in st.session_state:
        show_detail_page(st.session_state['selected_element'])
        return
        
    # Sidebar filters
    st.sidebar.header("Search Filters")
    search_query = st.sidebar.text_input("Search text (case-insensitive):", "")
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
            
            if e.metadata:
                for m in e.metadata:
                    if m.type == 'text' and m.value:
                        if query_lower in str(m.value).lower():
                            match_meta = True
                            break
            
            if match_text or match_meta:
                e._match_text = match_text
                e._match_meta = match_meta
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
                        
                        if e.type in ['illustration', 'painting']:
                            match_labels = []
                            if has_search:
                                if match_text:
                                    match_labels.append("content")
                                if match_meta:
                                    match_labels.append("metadata")
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
