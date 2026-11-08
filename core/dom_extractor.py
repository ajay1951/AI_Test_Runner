from playwright.sync_api import Page

class DOMExtractor:
    """Extracts interactive inputs, buttons, and selects with custom synthetic AI tags."""

    JS_SNIPPET = """
    () => {
        const elements = document.querySelectorAll(
            'input, button, select, textarea, a[href], [role="button"], [role="checkbox"], [role="radio"]'
        );
        const snapshot = [];
        let index = 0;

        elements.forEach(el => {
            const rect = el.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
            if (!isVisible) return;

            index++;
            const refId = `ref_${index}`;
            el.setAttribute('data-ai-id', refId);

            let labelText = '';
            if (el.id) {
                const label = document.querySelector(`label[for="${el.id}"]`);
                if (label) labelText = label.innerText.trim();
            }
            if (!labelText && el.closest('label')) {
                labelText = el.closest('label').innerText.trim();
            }

            snapshot.push({
                ref: refId,
                tag: el.tagName.toLowerCase(),
                type: el.getAttribute('type') || '',
                id: el.id || '',
                name: el.getAttribute('name') || '',
                placeholder: el.getAttribute('placeholder') || '',
                ariaLabel: el.getAttribute('aria-label') || '',
                text: (el.innerText || el.value || '').trim().substring(0, 50),
                associatedLabel: labelText
            });
        });
        return snapshot;
    }
    """

    @staticmethod
    def get_interactive_tree(page: Page) -> list[dict]:
        return page.evaluate(DOMExtractor.JS_SNIPPET)
