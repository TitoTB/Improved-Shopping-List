/** Consistent, accessible close controls for the panel's native dialogs. */
export function installDialogCloseButtons(root) {
  const style = document.createElement("style");
  style.textContent = `
    dialog .isl-dialog-close {
      position:absolute; inset-block-start:8px; inset-inline-end:8px;
      display:grid; place-items:center; width:40px; height:40px; min-height:40px;
      padding:8px; border:0; border-radius:50%; background:transparent;
      color:inherit; cursor:pointer; line-height:1; z-index:1;
    }
    dialog .isl-dialog-close:hover { background:var(--secondary-background-color,#edf2ef); }
    dialog .isl-dialog-close:focus-visible { outline:2px solid var(--primary-color,#217354); outline-offset:2px; }
    dialog .isl-dialog-close:disabled { cursor:default; opacity:.5; }
    dialog .isl-dialog-close svg { display:block; width:24px; height:24px; }
    dialog .isl-dialog-title { padding-inline-end:40px; }
  `;
  root.append(style);
  root.querySelectorAll("dialog").forEach(dialog => {
    const title = root.getElementById(dialog.getAttribute("aria-labelledby"));
    title?.classList.add("isl-dialog-title");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "isl-dialog-close";
    button.setAttribute("aria-label", "Cerrar ventana");
    button.title = "Cerrar";
    button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    button.addEventListener("click", () => {
      // Reuse Escape's existing busy guards and each dialog's close cleanup.
      if (dialog.dispatchEvent(new Event("cancel", { cancelable: true }))) dialog.close();
    });
    dialog.append(button);
  });
}
