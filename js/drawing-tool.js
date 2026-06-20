/**
 * Drawing Tool - Web Version
 * A standalone drawing tool for any webpage.
 *
 * Usage:
 *   <script src="drawing-tool.js"></script>
 *   <script>DrawingTool.init();</script>
 */
const DrawingTool = (function() {
  'use strict';

  let initialized = false;

  // State
  const state = {
    isDrawingMode: false,
    isDrawing: false,
    currentTool: 'pen',
    strokeSize: 8,
    strokeColor: '#ff0000',
    lastX: 0,
    lastY: 0,
    panelMinimized: false
  };

  // History for undo/redo
  const history = {
    states: [],
    index: -1,
    maxSize: 50
  };

  // Canvas elements
  let mainCanvas, mainCtx, drawCanvas, drawCtx, panel;

  function saveToHistory() {
    history.states = history.states.slice(0, history.index + 1);
    history.states.push(mainCanvas.toDataURL());
    history.index++;
    if (history.states.length > history.maxSize) {
      history.states.shift();
      history.index--;
    }
    updateUndoRedoButtons();
    saveToLocalStorage();
  }

  function undo() {
    if (history.index > 0) {
      history.index--;
      loadHistoryState(history.index);
      updateUndoRedoButtons();
    }
  }

  function redo() {
    if (history.index < history.states.length - 1) {
      history.index++;
      loadHistoryState(history.index);
      updateUndoRedoButtons();
    }
  }

  function loadHistoryState(index) {
    const img = new Image();
    img.onload = () => {
      mainCtx.clearRect(0, 0, mainCanvas.width, mainCanvas.height);
      mainCtx.drawImage(img, 0, 0);
    };
    img.src = history.states[index];
  }

  function updateUndoRedoButtons() {
    const undoBtn = document.getElementById('drawing-tool-undo');
    const redoBtn = document.getElementById('drawing-tool-redo');
    if (undoBtn) undoBtn.disabled = history.index <= 0;
    if (redoBtn) redoBtn.disabled = history.index >= history.states.length - 1;
  }

  function createCanvases() {
    // Main canvas (permanent drawings)
    mainCanvas = document.createElement('canvas');
    mainCanvas.id = 'drawing-tool-canvas';
    mainCanvas.style.cssText = 'position:absolute;top:0;left:0;z-index:10000;pointer-events:none;display:none;';
    document.body.appendChild(mainCanvas);
    mainCtx = mainCanvas.getContext('2d');

    // Draw canvas (active stroke)
    drawCanvas = document.createElement('canvas');
    drawCanvas.id = 'drawing-tool-active';
    drawCanvas.style.cssText = 'position:fixed;top:0;left:0;z-index:10001;pointer-events:none;';
    document.body.appendChild(drawCanvas);
    drawCtx = drawCanvas.getContext('2d', { desynchronized: true });
  }

  function createPanel() {
    panel = document.createElement('div');
    panel.id = 'drawing-tool-panel';
    panel.innerHTML = `
      <div id="drawing-tool-header">
        <span>Draw</span>
        <div>
          <button id="drawing-tool-minimize" title="Minimize">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg>
          </button>
          <button id="drawing-tool-close" title="Stop Drawing">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
      </div>
      <div id="drawing-tool-body">
        <div class="drawing-tool-section">
          <button class="drawing-tool-tool active" data-tool="pen" title="Pen (Ctrl+P)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/></svg>
          </button>
          <button class="drawing-tool-tool" data-tool="highlighter" title="Highlighter (Ctrl+H)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l-6 6v3h9l3-3"/><path d="M22 12l-4.6 4.6a2 2 0 01-2.8 0l-5.2-5.2a2 2 0 010-2.8L14 4"/></svg>
          </button>
          <button class="drawing-tool-tool" data-tool="eraser" title="Eraser (Ctrl+E)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 20H7L3 16c-.6-.6-.6-1.5 0-2.1l10-10c.6-.6 1.5-.6 2.1 0l6 6c.6.6.6 1.5 0 2.1L13 20"/><path d="M6 11l8 8"/></svg>
          </button>
        </div>
        <div class="drawing-tool-section" id="drawing-tool-colors">
          <button class="drawing-tool-color active" data-color="#ff0000" style="background:#ff0000" title="Red"></button>
          <button class="drawing-tool-color" data-color="#00ff00" style="background:#00ff00" title="Green"></button>
          <button class="drawing-tool-color" data-color="#0000ff" style="background:#0000ff" title="Blue"></button>
          <button class="drawing-tool-color" data-color="#ffff00" style="background:#ffff00" title="Yellow"></button>
          <button class="drawing-tool-color" data-color="#ff00ff" style="background:#ff00ff" title="Magenta"></button>
          <button class="drawing-tool-color" data-color="#ffa500" style="background:#ffa500" title="Orange"></button>
          <button class="drawing-tool-color" data-color="#000000" style="background:#000000" title="Black"></button>
          <button class="drawing-tool-color" data-color="#ffffff" style="background:#ffffff" title="White"></button>
          <button class="drawing-tool-color" data-color="#00ffff" style="background:#00ffff" title="Cyan"></button>
          <button class="drawing-tool-color" data-color="#ff69b4" style="background:#ff69b4" title="Pink"></button>
          <button class="drawing-tool-color" data-color="#800080" style="background:#800080" title="Purple"></button>
          <button class="drawing-tool-color" data-color="#8b4513" style="background:#8b4513" title="Brown"></button>
          <button class="drawing-tool-color" data-color="#808080" style="background:#808080" title="Gray"></button>
          <button class="drawing-tool-color" data-color="#32cd32" style="background:#32cd32" title="Lime"></button>
          <button class="drawing-tool-color" data-color="#000080" style="background:#000080" title="Navy"></button>
          <button class="drawing-tool-color" data-color="#ff7f50" style="background:#ff7f50" title="Coral"></button>
        </div>
        <div class="drawing-tool-section">
          <button class="drawing-tool-size" data-size="3" title="Small">S</button>
          <button class="drawing-tool-size active" data-size="8" title="Medium">M</button>
          <button class="drawing-tool-size" data-size="16" title="Large">L</button>
          <button class="drawing-tool-size" data-size="32" title="Extra Large">XL</button>
        </div>
        <div class="drawing-tool-section">
          <button id="drawing-tool-undo" title="Undo (Ctrl+Z)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 00-9-9 9 9 0 00-6 2.3L3 13"/></svg>
          </button>
          <button id="drawing-tool-redo" title="Redo (Ctrl+Y)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 019-9 9 9 0 016 2.3l3 2.7"/></svg>
          </button>
          <button id="drawing-tool-clear" title="Clear All">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(panel);
  }

  function createStyles() {
    const styles = document.createElement('style');
    styles.textContent = `
      #drawing-tool-panel {
        position: fixed;
        top: 60px;
        right: 20px;
        z-index: 10002;
        background: #1a1a2e;
        border-radius: 10px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        display: none;
        user-select: none;
        min-width: 180px;
      }
      #drawing-tool-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: #2a2a4e;
        border-radius: 10px 10px 0 0;
        cursor: move;
        color: #fff;
        font-size: 14px;
        font-weight: 500;
      }
      #drawing-tool-header > div {
        display: flex;
        gap: 4px;
      }
      #drawing-tool-header button {
        background: none;
        border: none;
        color: #fff;
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      #drawing-tool-header button:hover {
        background: rgba(255,255,255,0.1);
      }
      #drawing-tool-close:hover {
        background: rgba(255,100,100,0.3) !important;
      }
      #drawing-tool-body {
        padding: 10px;
      }
      #drawing-tool-panel.minimized #drawing-tool-body {
        display: none;
      }
      #drawing-tool-panel.minimized #drawing-tool-header {
        border-radius: 10px;
      }
      #drawing-tool-panel.minimized {
        min-width: auto;
      }
      .drawing-tool-section {
        display: flex;
        gap: 6px;
        margin-bottom: 8px;
        flex-wrap: wrap;
      }
      .drawing-tool-section:last-child {
        margin-bottom: 0;
      }
      .drawing-tool-tool, .drawing-tool-size, #drawing-tool-undo, #drawing-tool-redo, #drawing-tool-clear {
        width: 36px;
        height: 36px;
        border: 2px solid #333;
        border-radius: 6px;
        background: #2a2a3e;
        color: #fff;
        font-size: 14px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .drawing-tool-tool:hover, .drawing-tool-size:hover, #drawing-tool-undo:hover, #drawing-tool-redo:hover, #drawing-tool-clear:hover {
        background: #3a3a4e;
      }
      .drawing-tool-tool.active, .drawing-tool-size.active {
        border-color: #4CAF50;
        background: #2a3e2a;
      }
      .drawing-tool-color {
        width: 24px;
        height: 24px;
        border: 2px solid #333;
        border-radius: 4px;
        cursor: pointer;
      }
      .drawing-tool-color.active {
        border-color: #fff;
        box-shadow: 0 0 0 2px #4CAF50;
      }
      #drawing-tool-colors {
        display: grid;
        grid-template-columns: repeat(8, 24px);
        gap: 6px;
      }
      #drawing-tool-undo:disabled, #drawing-tool-redo:disabled {
        opacity: 0.4;
        cursor: not-allowed;
      }
    `;
    document.head.appendChild(styles);
  }

  function setupPanelEvents() {
    // Drag functionality
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    const header = panel.querySelector('#drawing-tool-header');
    header.addEventListener('mousedown', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      isDragging = true;
      dragOffsetX = e.clientX - panel.offsetLeft;
      dragOffsetY = e.clientY - panel.offsetTop;
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      panel.style.left = (e.clientX - dragOffsetX) + 'px';
      panel.style.top = (e.clientY - dragOffsetY) + 'px';
      panel.style.right = 'auto';
    });

    document.addEventListener('mouseup', () => {
      isDragging = false;
    });

    // Minimize
    panel.querySelector('#drawing-tool-minimize').addEventListener('click', () => {
      state.panelMinimized = !state.panelMinimized;
      panel.classList.toggle('minimized', state.panelMinimized);
      const minBtn = panel.querySelector('#drawing-tool-minimize');
      minBtn.innerHTML = state.panelMinimized
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg>';
    });

    // Close
    panel.querySelector('#drawing-tool-close').addEventListener('click', () => {
      setDrawingMode(false);
    });

    // Tools
    panel.querySelectorAll('.drawing-tool-tool').forEach(btn => {
      btn.addEventListener('click', () => setTool(btn.dataset.tool));
    });

    // Colors
    panel.querySelectorAll('.drawing-tool-color').forEach(btn => {
      btn.addEventListener('click', () => setColor(btn.dataset.color));
    });

    // Sizes
    panel.querySelectorAll('.drawing-tool-size').forEach(btn => {
      btn.addEventListener('click', () => setSize(parseInt(btn.dataset.size)));
    });

    // Undo/Redo/Clear
    panel.querySelector('#drawing-tool-undo').addEventListener('click', undo);
    panel.querySelector('#drawing-tool-redo').addEventListener('click', redo);
    panel.querySelector('#drawing-tool-clear').addEventListener('click', () => {
      if (confirm('Clear all drawings?')) {
        clearCanvas();
        saveToHistory();
      }
    });
  }

  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (!state.isDrawingMode) return;
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 'z': e.preventDefault(); undo(); break;
          case 'y': e.preventDefault(); redo(); break;
          case 'h': e.preventDefault(); setTool('highlighter'); break;
          case 'p': e.preventDefault(); setTool('pen'); break;
          case 'e': e.preventDefault(); setTool('eraser'); break;
        }
      }
    });
  }

  function resizeMainCanvas() {
    const w = Math.max(document.body.scrollWidth, window.innerWidth);
    const h = Math.max(document.body.scrollHeight, window.innerHeight);
    if (mainCanvas.width === w && mainCanvas.height === h) return;
    const imageData = mainCtx.getImageData(0, 0, mainCanvas.width, mainCanvas.height);
    mainCanvas.width = w;
    mainCanvas.height = h;
    mainCanvas.style.width = w + 'px';
    mainCanvas.style.height = h + 'px';
    mainCtx.putImageData(imageData, 0, 0);
  }

  function resizeDrawCanvas() {
    drawCanvas.width = window.innerWidth;
    drawCanvas.height = window.innerHeight;
    drawCanvas.style.width = window.innerWidth + 'px';
    drawCanvas.style.height = window.innerHeight + 'px';
  }

  function setupResizeHandler() {
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        resizeMainCanvas();
        resizeDrawCanvas();
      }, 300);
    });
  }

  function getViewportCoords(e) {
    const touch = e.touches?.[0];
    return {
      x: touch?.clientX ?? e.clientX,
      y: touch?.clientY ?? e.clientY
    };
  }

  function setDrawingMode(enabled) {
    state.isDrawingMode = enabled;
    drawCanvas.style.pointerEvents = enabled ? 'auto' : 'none';
    panel.style.display = enabled ? 'block' : 'none';
    mainCanvas.style.display = enabled ? 'block' : 'none';
    updateCursor();
    if (enabled && history.states.length === 0) {
      saveToHistory();
    }
  }

  function updateCursor() {
    drawCanvas.style.cursor = state.isDrawingMode ?
      (state.currentTool === 'eraser' ? 'cell' : 'crosshair') : 'default';
  }

  function setTool(tool) {
    state.currentTool = tool;
    panel.querySelectorAll('.drawing-tool-tool').forEach(b => {
      b.classList.toggle('active', b.dataset.tool === tool);
    });
    updateCursor();
  }

  function setColor(color) {
    state.strokeColor = color;
    panel.querySelectorAll('.drawing-tool-color').forEach(b => {
      b.classList.toggle('active', b.dataset.color === color);
    });
  }

  function setSize(size) {
    state.strokeSize = size;
    panel.querySelectorAll('.drawing-tool-size').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.size) === size);
    });
  }

  function setupDrawContext() {
    drawCtx.lineCap = 'round';
    drawCtx.lineJoin = 'round';
    drawCtx.lineWidth = state.strokeSize;
    drawCtx.strokeStyle = state.strokeColor;
    drawCtx.globalAlpha = 1;
    if (state.currentTool === 'eraser') {
      drawCtx.strokeStyle = 'rgba(180,180,180,0.7)';
    }
    drawCanvas.style.opacity = state.currentTool === 'highlighter' ? '0.25' : '1';
  }

  function startDrawing(e) {
    if (!state.isDrawingMode) return;
    state.isDrawing = true;
    const p = getViewportCoords(e);
    state.lastX = p.x;
    state.lastY = p.y;
    drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    setupDrawContext();
    drawCtx.beginPath();
    drawCtx.arc(p.x, p.y, state.strokeSize / 2, 0, Math.PI * 2);
    drawCtx.fillStyle = drawCtx.strokeStyle;
    drawCtx.fill();
  }

  function draw(e) {
    if (!state.isDrawing) return;
    e.preventDefault();
    const p = getViewportCoords(e);
    drawCtx.beginPath();
    drawCtx.moveTo(state.lastX, state.lastY);
    drawCtx.lineTo(p.x, p.y);
    drawCtx.stroke();
    state.lastX = p.x;
    state.lastY = p.y;
  }

  function stopDrawing() {
    if (!state.isDrawing) return;
    state.isDrawing = false;
    transferToMain();
    drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    saveToHistory();
  }

  function transferToMain() {
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    drawCanvas.style.opacity = '1';

    if (state.currentTool === 'eraser') {
      mainCtx.globalCompositeOperation = 'destination-out';
      mainCtx.drawImage(drawCanvas, scrollX, scrollY);
      mainCtx.globalCompositeOperation = 'source-over';
    } else if (state.currentTool === 'highlighter') {
      mainCtx.globalAlpha = 0.25;
      mainCtx.drawImage(drawCanvas, scrollX, scrollY);
      mainCtx.globalAlpha = 1;
    } else {
      mainCtx.drawImage(drawCanvas, scrollX, scrollY);
    }
  }

  function setupDrawingEvents() {
    drawCanvas.addEventListener('mousedown', startDrawing);
    drawCanvas.addEventListener('mousemove', draw);
    drawCanvas.addEventListener('mouseup', stopDrawing);
    drawCanvas.addEventListener('mouseleave', stopDrawing);
    drawCanvas.addEventListener('touchstart', startDrawing, { passive: false });
    drawCanvas.addEventListener('touchmove', draw, { passive: false });
    drawCanvas.addEventListener('touchend', stopDrawing);

    // Allow scrolling through the canvas
    drawCanvas.addEventListener('wheel', (e) => {
      // Scroll the window or iframe beneath
      window.scrollBy(0, e.deltaY);
    }, { passive: true });
  }

  function clearCanvas() {
    mainCtx.clearRect(0, 0, mainCanvas.width, mainCanvas.height);
  }

  // LocalStorage functions
  function getStorageKey() {
    return 'drawing_tool_' + location.hostname + location.pathname;
  }

  function saveToLocalStorage() {
    try {
      localStorage.setItem(getStorageKey(), mainCanvas.toDataURL());
    } catch (e) {
      console.warn('Drawing Tool: Could not save to localStorage', e);
    }
  }

  function loadFromLocalStorage() {
    try {
      const data = localStorage.getItem(getStorageKey());
      if (data) {
        const img = new Image();
        img.onload = () => {
          mainCtx.drawImage(img, 0, 0);
          saveToHistory();
        };
        img.src = data;
      }
    } catch (e) {
      console.warn('Drawing Tool: Could not load from localStorage', e);
    }
  }

  // Public API
  return {
    init: function(options = {}) {
      if (initialized) {
        console.warn('Drawing Tool already initialized');
        return this;
      }

      createCanvases();
      createPanel();
      createStyles();
      setupPanelEvents();
      setupKeyboardShortcuts();
      setupDrawingEvents();
      setupResizeHandler();

      resizeMainCanvas();
      resizeDrawCanvas();

      if (options.autoLoad !== false) {
        loadFromLocalStorage();
      }

      initialized = true;
      console.log('Drawing Tool initialized');
      return this;
    },

    enable: function() {
      setDrawingMode(true);
      return this;
    },

    disable: function() {
      setDrawingMode(false);
      return this;
    },

    toggle: function() {
      setDrawingMode(!state.isDrawingMode);
      return this;
    },

    clear: function() {
      clearCanvas();
      saveToHistory();
      return this;
    },

    setTool: setTool,
    setColor: setColor,
    setSize: setSize,
    undo: undo,
    redo: redo,

    isEnabled: function() {
      return state.isDrawingMode;
    },

    getState: function() {
      return { ...state };
    }
  };
})();
