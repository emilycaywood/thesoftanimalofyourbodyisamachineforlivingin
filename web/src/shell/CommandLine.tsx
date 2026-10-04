// Rhino-style command line / command palette: autocomplete, recent commands,
// Enter or Space on an empty line repeats the last command, Ctrl+K focuses it,
// and typing in the viewport lands here.
import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { allCommands, execute, hooks, lastCommandName, matchCommands, parseArgs, recent, repeatLast, findCommand } from "@/commands/registry";
import { Kbd } from "@/components/ui";
import { useLab } from "@/store/lab";

export function CommandLine() {
  const server = useLab((s) => s.commands);
  const lastLog = useLab((s) => s.logs[s.logs.length - 1]);
  const commands = useMemo(() => allCommands(server), [server]);
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    hooks.focusCommandLine = () => {
      input.current?.focus();
      setOpen(true);
    };
  }, []);

  const word = text.trim().split(/\s+/)[0] ?? "";
  const matches = useMemo(() => {
    if (!word) return recent.map((n) => findCommand(n, commands)).filter((c): c is NonNullable<typeof c> => Boolean(c));
    return matchCommands(word, commands).slice(0, 12);
  }, [word, commands]);

  const submit = (name?: string) => {
    const parts = text.trim().split(/\s+/).filter(Boolean);
    const target = name ?? matches[index]?.name ?? parts[0];
    if (!target) {
      repeatLast();
      return;
    }
    const args = parseArgs(parts.slice(1));
    setText("");
    setOpen(false);
    setIndex(0);
    input.current?.blur();
    void execute(target, Object.keys(args).length ? args : undefined);
  };

  return (
    <div className="relative flex h-7 shrink-0 items-center gap-2 border-b border-line bg-bg2 px-2" data-testid="command-line">
      <span className="font-mono text-dim">Command:</span>
      <input
        ref={input}
        type="text"
        className="min-w-0 flex-1 border-0 bg-transparent font-mono"
        placeholder={lastCommandName() ? `Enter or Space repeats ${lastCommandName()}` : "Type a command (try Simulate, Bake, ZoomExtents)..."}
        value={text}
        spellCheck={false}
        data-testid="command-input"
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => {
          setText(e.target.value);
          setIndex(0);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || (e.key === " " && text.trim() === "")) {
            e.preventDefault();
            submit();
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            setIndex((i) => Math.min(i + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setIndex((i) => Math.max(i - 1, 0));
          } else if (e.key === "Tab" && matches[index]) {
            e.preventDefault();
            setText(matches[index].name + " ");
          } else if (e.key === "Escape") {
            setText("");
            setOpen(false);
            input.current?.blur();
          }
          e.stopPropagation();
        }}
      />
      <span className={clsx("max-w-[45%] truncate font-mono text-[11px]", lastLog?.level === "error" ? "text-err" : "text-dim")} title={lastLog?.message} data-testid="last-log">
        {lastLog?.message}
      </span>
      <span className="text-dim"><Kbd>Ctrl</Kbd> <Kbd>K</Kbd></span>
      {open && matches.length > 0 && (
        <div className="absolute top-7 left-20 z-40 w-[520px] rounded border border-line bg-bg2 shadow-xl" data-testid="command-list">
          {!word && <div className="px-2 py-0.5 text-[10px] text-dim uppercase">Recent</div>}
          {matches.map((c, i) => (
            <div
              key={c.name}
              className={clsx("flex cursor-default items-center gap-2 px-2 py-0.5", i === index && "bg-accent/25")}
              onMouseDown={(e) => {
                e.preventDefault();
                submit(c.name);
              }}
              onMouseEnter={() => setIndex(i)}
            >
              <span className="w-44 shrink-0 truncate font-mono">{c.name}</span>
              <span className="flex-1 truncate text-dim">{c.description}</span>
              <span className="text-[10px] text-dim">{c.category}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
