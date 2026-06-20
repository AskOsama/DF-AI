/**
 * Drawing-tool init for the DS-AI 2026 course.
 *
 * Loads after js/drawing-tool.js. Initialises the tool, then mounts a
 * small floating "✏︎" button at the bottom-right of the viewport that
 * toggles the annotation panel on or off.
 *
 * The instructor presses it to start drawing on the page (highlighter,
 * pen, eraser, undo, etc.) during a live explanation. Students who
 * never click it see only the discreet button. Keyboard shortcut: Alt+D.
 */
(function () {
  'use strict';

  function mount() {
    if (typeof DrawingTool === 'undefined') {
      console.warn('[drawing-tool-init] DrawingTool global missing — was drawing-tool.js loaded first?');
      return;
    }

    // Don't double-mount if this script is included twice
    if (document.getElementById('dt-toggle')) {
      return;
    }

    try {
      DrawingTool.init();
    } catch (err) {
      console.error('[drawing-tool-init] DrawingTool.init() threw:', err);
      return;
    }

    var btn = document.createElement('button');
    btn.id = 'dt-toggle';
    btn.type = 'button';
    btn.title = 'Annotate this page (Alt+D)';
    btn.setAttribute('aria-label', 'Toggle annotation tools');
    btn.textContent = '✏';

    // Inline styles via cssText — most universal, ignores any cascade
    btn.style.cssText = [
      'position:fixed',
      'bottom:20px',
      'right:20px',                          // works in LTR + RTL alike
      'z-index:2147483600',                  // top of the stack
      'width:48px',
      'height:48px',
      'border-radius:50%',
      'border:1px solid #d6cdb8',
      'background:#fbf8f0',
      'color:#14202e',
      'cursor:pointer',
      'font-size:22px',
      'line-height:1',
      'padding:0',
      'box-shadow:0 4px 14px rgba(20,32,46,0.22)',
      'transition:background 0.18s ease, color 0.18s ease, transform 0.18s ease',
      'font-family:system-ui, -apple-system, sans-serif',
      'display:flex',
      'align-items:center',
      'justify-content:center'
    ].join(';') + ';';

    btn.addEventListener('mouseenter', function () {
      btn.style.background = '#a07c1d';
      btn.style.color = '#fff';
      btn.style.transform = 'translateY(-2px)';
    });
    btn.addEventListener('mouseleave', function () {
      var on = btn.dataset.active === '1';
      btn.style.background = on ? '#14202e' : '#fbf8f0';
      btn.style.color = on ? '#fff' : '#14202e';
      btn.style.transform = 'none';
    });
    btn.addEventListener('click', function () {
      DrawingTool.toggle();
      var on = DrawingTool.isEnabled();
      btn.dataset.active = on ? '1' : '0';
      btn.title = on ? 'Stop annotating (Alt+D)' : 'Annotate this page (Alt+D)';
      btn.style.background = on ? '#14202e' : '#fbf8f0';
      btn.style.color = on ? '#fff' : '#14202e';
    });

    document.body.appendChild(btn);

    // Keyboard shortcut Alt+D
    document.addEventListener('keydown', function (e) {
      if (e.altKey && (e.key === 'd' || e.key === 'D')) {
        e.preventDefault();
        btn.click();
      }
    });

    // Hide the button when printing
    var printStyle = document.createElement('style');
    printStyle.textContent = '@media print { #dt-toggle { display: none !important; } }';
    document.head.appendChild(printStyle);

    console.log('[drawing-tool-init] Toggle button mounted. Click ✏ bottom-right or press Alt+D.');
  }

  // Wait until the body is parsed before mounting
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
