// syntax.js — подсветка Java-кода через регулярные выражения
(function () {
    'use strict';

    function escapeHtml(s) {
        return s.replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
    }

    const TOKEN_REGEX = new RegExp(
        [
            /(\/\*[\s\S]*?\*\/)|(\/\/[^\n]*)/.source,
            /("(?:\\.|[^"\\])*")|('(?:\\.|[^'\\])*')/.source,
            /(@[A-Za-z_]\w*)/.source,
            /\b(class|interface|enum|extends|implements|record)\b/.source,
            /\b(for|while|do|if|else|switch|case|default|break|continue|return|try|catch|finally|throw|new|instanceof|synchronized|volatile|transient|native|assert|yield)\b/.source,
            /\b(public|private|protected|static|final|abstract|strictfp|package|import|void|boolean|byte|char|short|int|long|float|double|this|super|true|false|null)\b/.source,
            /\b(0x[0-9a-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?[fFdDlL]?)\b/.source,
            /([A-Za-z_$][\w$]*)/.source
        ].join('|'),
        'g'
    );

    function highlightJava(code) {
        if (!code) return '\n';
        let out = '';
        let lastIndex = 0;
        let m;
        TOKEN_REGEX.lastIndex = 0;

        while ((m = TOKEN_REGEX.exec(code)) !== null) {
            const before = code.slice(lastIndex, m.index);
            if (before) out += escapeHtml(before);

            const match = m[0];
            if (m[1] || m[2]) {
                out += '<span class="tok-comment">' + escapeHtml(match) + '</span>';
            } else if (m[3] || m[4]) {
                out += '<span class="tok-string">' + escapeHtml(match) + '</span>';
            } else if (m[5]) {
                out += '<span class="tok-annotation">' + escapeHtml(match) + '</span>';
            } else if (m[6]) {
                out += '<span class="tok-class">' + escapeHtml(match) + '</span>';
            } else if (m[7]) {
                out += '<span class="tok-keyword">' + escapeHtml(match) + '</span>';
            } else if (m[8]) {
                out += '<span class="tok-operator">' + escapeHtml(match) + '</span>';
            } else if (m[9]) {
                out += '<span class="tok-number">' + escapeHtml(match) + '</span>';
            } else if (m[10]) {
                out += '<span class="tok-variable">' + escapeHtml(match) + '</span>';
            } else {
                out += escapeHtml(match);
            }
            lastIndex = m.index + match.length;
        }
        if (lastIndex < code.length) out += escapeHtml(code.slice(lastIndex));
        return out + '\n';
    }

    function renderHighlight(textarea) {
        if (!textarea) return;
        const highlight = textarea.parentElement?.querySelector('.editor-highlight');
        if (!highlight) return;

        highlight.innerHTML = highlightJava(textarea.value);
        highlight.scrollTop = textarea.scrollTop;
        highlight.scrollLeft = textarea.scrollLeft;
    }

    function attachHighlight(textarea) {
        if (!textarea || textarea.__highlightAttached) return;
        textarea.__highlightAttached = true;

        const highlight = textarea.parentElement?.querySelector('.editor-highlight');
        if (!highlight) return;

        textarea.addEventListener('scroll', () => {
            highlight.scrollTop = textarea.scrollTop;
            highlight.scrollLeft = textarea.scrollLeft;
        });

        textarea.addEventListener('input', () => renderHighlight(textarea));
        renderHighlight(textarea);
    }

    window.JavaHighlight = {
        renderHighlight,
        attachHighlight,
    };
})();