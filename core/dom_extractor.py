"""
Generic DOM Understanding & Interactive Element Extractor.
Extracts accessible names, roles, ARIA attributes, labels, placeholders, and bounding states
without relying on site-specific assumptions or brittle selectors.
"""

from playwright.sync_api import Page
from typing import List, Dict, Any


class DOMExtractor:
    """
    Extracts visible interactive inputs, buttons, links, selects, and controls
    annotating them with lightweight synthetic AI reference tags (data-ai-id).
    """

    JS_SNIPPET = """
    () => {
        const snapshot = [];
        let index = 0;

        function processDocument(doc, framePrefix = '') {
            if (!doc) return;

            const elements = doc.querySelectorAll(
                'input, button, select, textarea, a[href], [role="button"], [role="checkbox"], [role="radio"], [role="combobox"], [role="link"], [role="tab"], [tabindex="0"]'
            );

            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = rect.width > 0 && rect.height > 0 && 
                                  style.visibility !== 'hidden' && 
                                  style.display !== 'none' && 
                                  parseFloat(style.opacity || '1') > 0.05;

                if (!isVisible) return;

                index++;
                const refId = `ref_${index}`;
                el.setAttribute('data-ai-id', refId);

                // 1. Associated label discovery
                let labelText = '';
                if (el.id) {
                    const label = doc.querySelector(`label[for="${el.id}"]`);
                    if (label) labelText = label.innerText.trim();
                }
                if (!labelText && el.closest('label')) {
                    labelText = el.closest('label').innerText.trim();
                }
                if (!labelText && el.getAttribute('aria-labelledby')) {
                    const labeledBy = doc.getElementById(el.getAttribute('aria-labelledby'));
                    if (labeledBy) labelText = labeledBy.innerText.trim();
                }

                // 2. Element text and roles
                const explicitRole = el.getAttribute('role') || '';
                const nativeTag = el.tagName.toLowerCase();
                const computedRole = explicitRole || (
                    nativeTag === 'button' ? 'button' :
                    nativeTag === 'a' ? 'link' :
                    nativeTag === 'select' ? 'combobox' :
                    (nativeTag === 'input' && ['checkbox', 'radio'].includes(el.type)) ? el.type :
                    nativeTag === 'input' ? 'textbox' : nativeTag
                );

                const visibleText = (el.innerText || el.value || '').trim();

                snapshot.push({
                    ref: refId,
                    tag: nativeTag,
                    type: el.getAttribute('type') || '',
                    role: computedRole,
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    text: visibleText,
                    associatedLabel: labelText,
                    isEnabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
                    isChecked: el.checked === true || el.getAttribute('aria-checked') === 'true',
                    inViewport: (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                    )
                });
            });

            // Inspect accessible iframes
            const iframes = doc.querySelectorAll('iframe');
            iframes.forEach((frame, fIdx) => {
                try {
                    if (frame.contentDocument) {
                        processDocument(frame.contentDocument, `frame_${fIdx}_`);
                    }
                } catch(e) {
                    // Cross-origin iframe security boundary; skip
                }
            });
        }

        processDocument(document);
        return snapshot;
    }
    """

    @staticmethod
    def get_interactive_tree(page: Page) -> List[Dict[str, Any]]:
        """Evaluates live page DOM and returns list of interactive element descriptors."""
        try:
            return page.evaluate(DOMExtractor.JS_SNIPPET)
        except Exception:
            return []
