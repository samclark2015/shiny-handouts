/**
 * Shared utilities for Mermaid mindmap rendering
 */

const MindmapUtils = {
  _renderCounter: 0,

  /**
   * Initialize Mermaid with given options
   */
  initMermaid(theme = 'default', padding = 40) {
    mermaid.initialize({
      startOnLoad: false,
      theme: theme,
      mindmap: { padding: parseInt(padding), useMaxWidth: false },
      securityLevel: 'loose',
      flowchart: { useMaxWidth: false },
      logLevel: 'error'
    });
  },

  /**
   * Render a single mermaid diagram
   */
  async renderDiagram(elementId, code, svgIdPrefix) {
    const element = document.getElementById(elementId);
    if (!element) {
      console.error('Mermaid: Element not found:', elementId);
      return false;
    }
    if (!code || !code.trim()) {
      console.error('Mermaid: No code provided');
      return false;
    }

    // Generate unique ID for each render to avoid conflicts
    this._renderCounter++;
    const svgId = `${svgIdPrefix}-${this._renderCounter}`;

    try {
      const { svg } = await mermaid.render(svgId, code);
      element.innerHTML = svg;
      return true;
    } catch (error) {
      console.error('Mermaid rendering error:', error);
      // Show the code and error for debugging
      element.innerHTML = `<div style="color: red; padding: 1rem;">
        <strong>Diagram rendering failed:</strong> ${error.message || error}
      </div>
      <pre style="background: #f5f5f5; padding: 1rem; overflow: auto;">${this._escapeHtml(code)}</pre>`;
      return false;
    }
  },

  /**
   * Escape HTML entities for safe display
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  /**
   * Download a diagram as PNG
   */
  downloadPNG(svgSelector, filename) {
    const svg = document.querySelector(svgSelector);
    if (!svg) {
      alert('Diagram not rendered yet. Please wait.');
      return;
    }

    const svgData = new XMLSerializer().serializeToString(svg);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = function () {
      const scale = 2;
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;
      ctx.scale(scale, scale);
      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);

      const pngUrl = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = pngUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    };

    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
  },

  /**
   * Apply zoom transform to mermaid element
   */
  applyZoom(selector, zoomPercent) {
    const element = document.querySelector(selector);
    if (element) {
      element.style.transform = `scale(${zoomPercent / 100})`;
    }
  }
};
