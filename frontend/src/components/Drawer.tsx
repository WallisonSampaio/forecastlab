/**
 * Right sheet (spec §2.3.6): `role="dialog"`, focus trap, Esc closes, focus returns to the
 * element that opened it. The page behind is only dimmed (not blurred) so its context stays
 * readable next to the sheet. Rendered in a portal so no transformed/blurred ancestor can clip it.
 *
 * The body scrolls; `footer` (optional) stays pinned at the bottom (e.g. the "Ficha da série"
 * action bar). A dialog opened on top of the drawer (a `Modal`) keeps its own keys: Tab and Esc
 * are ignored here while another `[role="dialog"][aria-modal="true"]` is open, or when pressed
 * inside another `[role="dialog"]`.
 */
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(",");

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.closest('[aria-hidden="true"], [inert]'),
  );
}

export interface DrawerProps {
  open: boolean;
  title: string;
  onClose: () => void;
  /** Sheet width in px (default 560). Never wider than the viewport. */
  width?: number;
  /** Optional line under the title. */
  subtitle?: ReactNode;
  /** Optional bar pinned to the bottom of the sheet. */
  footer?: ReactNode;
  children: ReactNode;
}

export function Drawer({ open, title, onClose, width = 560, subtitle, footer, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Initial focus, scroll lock and focus restore.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    if (panel) (focusables(panel)[0] ?? panel).focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      if (opener && opener.isConnected) opener.focus();
    };
  }, [open]);

  // Focus trap + Esc.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel) return;
      const target = e.target instanceof Element ? e.target : null;
      const dialog = target?.closest('[role="dialog"]');
      if (dialog && dialog !== panel) return; // a dialog on top handles its own keys
      // A modal opened from the sheet (e.g. "Criar ajuste comercial") owns Esc and Tab even when
      // focus is still on the sheet's button: Esc must close only that modal.
      const modals = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
      for (const m of Array.from(modals)) if (m !== panel && !m.contains(panel)) return;
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables(panel);
      if (!items.length) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!active || !panel.contains(active)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && (active === first || active === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        aria-hidden="true"
        className="drawer-backdrop absolute inset-0 bg-[#1b1f3b]/20"
        onMouseDown={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ width }}
        className="drawer-panel relative flex h-full max-w-[calc(100vw-2rem)] flex-col rounded-l-3xl bg-white shadow-[-24px_0_60px_-24px_rgba(45,50,119,0.35)] outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="break-words text-[17px] font-semibold leading-snug text-ink">
              {title}
            </h2>
            {subtitle && <div className="mt-1 text-xs leading-relaxed text-muted">{subtitle}</div>}
          </div>
          <button
            type="button"
            className="btn-ghost shrink-0 px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            onClick={onClose}
            aria-label="Fechar"
            title="Fechar (Esc)"
          >
            <X size={16} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <footer className="border-t border-line bg-white px-6 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
