async () => {
    // Function to check if element is visible
    const isVisible = (elem) => {
        const style = window.getComputedStyle(elem);
        return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
    };

    // Aitosoft 2026-08-06: never remove the document's own structure. Every
    // rule below walks `querySelectorAll("*")`, which includes <html> and
    // <body>, and the scroll-lock pattern a real CMP uses is literally
    // `body { position: fixed }` — so `removeFixedElements` below could select
    // the body on exactly the pages this script exists for. Same guard, same
    // reasoning as remove_consent_popups.js; see
    // tasks/done/consent-scripts-delete-the-page.md.
    const isStructural = (el) =>
        !!el &&
        (el === document.documentElement || el === document.body || el === document.head);

    // Aitosoft 2026-08-06: the alpha of a computed background colour, or 1 when
    // it is opaque or unparseable.
    //
    // This exists because `style.backgroundColor.includes("rgba")` — what the
    // size-and-appearance clause below used to test — is TRUE for every element
    // with a transparent background, which is the browser default:
    // getComputedStyle returns the literal string `rgba(0, 0, 0, 0)`. The whole
    // clause was therefore a no-op and the rule degenerated to "remove every
    // visible fixed-or-absolute element". Measured 2026-08-06: it deleted an
    // absolutely-positioned hero containing the contacts at success:true, with
    // 98% of the markdown still present, so nothing downstream could see it.
    //
    // The clause's evident intent is a modal scrim — a translucent backdrop —
    // and that is 0 < alpha < 1. Fully transparent is not a scrim; opaque is
    // not one either, and an opaque overlay still has the two size tests.
    const backdropAlpha = (style) => {
        const m = /rgba?\(([^)]+)\)/.exec(style.backgroundColor || "");
        if (!m) return 1;
        const parts = m[1].split(",");
        if (parts.length < 4) return 1;
        const a = parseFloat(parts[3]);
        return Number.isFinite(a) ? a : 1;
    };

    // Common selectors for popups and overlays
    const commonSelectors = [
        // Close buttons first
        'button[class*="close" i]',
        'button[class*="dismiss" i]',
        'button[aria-label*="close" i]',
        'button[title*="close" i]',
        'a[class*="close" i]',
        'span[class*="close" i]',

        // Cookie notices
        '[class*="cookie-banner" i]',
        '[id*="cookie-banner" i]',
        '[class*="cookie-consent" i]',
        '[id*="cookie-consent" i]',

        // Newsletter/subscription dialogs
        '[class*="newsletter" i]',
        '[class*="subscribe" i]',

        // Generic popups/modals
        '[class*="popup" i]',
        '[class*="modal" i]',
        '[class*="overlay" i]',
        '[class*="dialog" i]',
        '[role="dialog"]',
        '[role="alertdialog"]',
    ];

    // Try to click close buttons first
    for (const selector of commonSelectors.slice(0, 6)) {
        const closeButtons = document.querySelectorAll(selector);
        for (const button of closeButtons) {
            if (isVisible(button)) {
                try {
                    button.click();
                    await new Promise((resolve) => setTimeout(resolve, 100));
                } catch (e) {
                    console.log("Error clicking button:", e);
                }
            }
        }
    }

    // Remove remaining overlay elements
    const removeOverlays = () => {
        // Find elements with high z-index
        const allElements = document.querySelectorAll("*");
        for (const elem of allElements) {
            if (isStructural(elem)) continue;
            const style = window.getComputedStyle(elem);
            const zIndex = parseInt(style.zIndex);
            const position = style.position;
            const alpha = backdropAlpha(style);

            if (
                isVisible(elem) &&
                (zIndex > 999 || position === "fixed" || position === "absolute") &&
                (elem.offsetWidth > window.innerWidth * 0.5 ||
                    elem.offsetHeight > window.innerHeight * 0.5 ||
                    (alpha > 0 && alpha < 1) ||
                    parseFloat(style.opacity) < 1)
            ) {
                elem.remove();
            }
        }

        // Remove elements matching common selectors
        for (const selector of commonSelectors) {
            const elements = document.querySelectorAll(selector);
            elements.forEach((elem) => {
                if (isVisible(elem) && !isStructural(elem)) {
                    elem.remove();
                }
            });
        }
    };

    // Remove overlay elements
    removeOverlays();

    // Remove any fixed/sticky position elements at the top/bottom
    const removeFixedElements = () => {
        const elements = document.querySelectorAll("*");
        elements.forEach((elem) => {
            if (isStructural(elem)) return;
            const style = window.getComputedStyle(elem);
            if ((style.position === "fixed" || style.position === "sticky") && isVisible(elem)) {
                elem.remove();
            }
        });
    };

    removeFixedElements();

    // Remove empty block elements as: div, p, span, etc.
    const removeEmptyBlockElements = () => {
        const blockElements = document.querySelectorAll(
            "div, p, span, section, article, header, footer, aside, nav, main, ul, ol, li, dl, dt, dd, h1, h2, h3, h4, h5, h6"
        );
        blockElements.forEach((elem) => {
            if (elem.innerText.trim() === "") {
                elem.remove();
            }
        });
    };

    // Remove margin-right and padding-right from body (often added by modal
    // scripts). Null-guarded: the page's own scripts can remove <body>, and an
    // unguarded access then throws a TypeError that aborts the snippet silently.
    if (document.body) {
        document.body.style.marginRight = "0px";
        document.body.style.paddingRight = "0px";
        document.body.style.overflow = "auto";

        // Wait a bit for any animations to complete
        document.body.scrollIntoView(false);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
};
