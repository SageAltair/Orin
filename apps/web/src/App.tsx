import { ArrowUpRight, Command, Compass, Layers3, Sparkles } from "lucide-react";

const principles = [
  { icon: Compass, title: "Intent, clearly held", detail: "A considered place for what matters next." },
  { icon: Layers3, title: "Context, thoughtfully arranged", detail: "The right pieces, ready when you need them." },
  { icon: Sparkles, title: "Execution, with you in control", detail: "A future shaped around your direction." },
];

export default function App() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#0b0f0e] text-white selection:bg-emerald-300 selection:text-[#0b0f0e]">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(52,111,82,0.2),transparent_45%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-7xl flex-col px-6 sm:px-10">
        <header className="flex h-20 items-center justify-between border-b border-white/[0.08]">
          <a className="flex items-center gap-2.5 text-sm font-semibold tracking-[0.18em]" href="#home" aria-label="Orin home">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-300 text-[#0b0f0e]"><Command size={15} strokeWidth={2.5} /></span>
            ORIN
          </a>
          <span className="rounded-full border border-white/10 px-3 py-1.5 text-[11px] tracking-wide text-white/50">A NEW WAY TO MOVE FORWARD</span>
        </header>
        <section id="home" className="flex flex-1 flex-col items-center justify-center py-24 text-center">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-emerald-200/15 bg-emerald-200/[0.06] px-3.5 py-2 text-xs text-emerald-100/80">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_12px_#6ee7b7]" />
            Your personal execution environment
          </div>
          <h1 className="max-w-4xl text-balance text-5xl font-medium leading-[1.08] tracking-[-0.055em] sm:text-7xl lg:text-[88px]">Make room for<br /><span className="bg-gradient-to-r from-emerald-200 via-emerald-100 to-white/70 bg-clip-text text-transparent">what comes next.</span></h1>
          <p className="mt-7 max-w-xl text-base leading-7 text-white/50 sm:text-lg">A calmer way to turn intention into progress. Orin brings your direction and the work ahead into focus.</p>
          <a href="#principles" className="group mt-10 inline-flex items-center gap-2 rounded-full bg-emerald-200 px-5 py-3 text-sm font-medium text-[#102019] transition hover:bg-emerald-100">Discover Orin <ArrowUpRight size={16} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></a>
          <div id="principles" className="mt-24 grid w-full max-w-4xl gap-3 text-left md:grid-cols-3">
            {principles.map(({ icon: Icon, title, detail }, index) => (
              <article key={title} className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-5 transition hover:border-emerald-200/20 hover:bg-white/[0.04]">
                <div className="mb-8 flex items-center justify-between"><Icon size={18} className="text-emerald-200/80" /><span className="font-mono text-[10px] text-white/25">0{index + 1}</span></div>
                <h2 className="text-sm font-medium text-white/85">{title}</h2><p className="mt-1.5 text-xs leading-5 text-white/40">{detail}</p>
              </article>
            ))}
          </div>
        </section>
        <footer className="flex h-16 items-center justify-between border-t border-white/[0.08] text-[11px] text-white/30"><span>Designed around your direction.</span><span>© Orin</span></footer>
      </div>
    </main>
  );
}
