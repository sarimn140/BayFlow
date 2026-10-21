'use client'

import { ArrowRight, Bot, MessageCircle, RotateCcw, Send, X } from 'lucide-react'
import Link from 'next/link'
import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

import { Button } from '@/components/ui/button'
import { answerQuestion } from '@/features/help/engine'
import { STARTER_QUESTIONS, WELCOME_TEXT, type HelpLink } from '@/features/help/knowledge'
import { cn } from '@/lib/utils'

interface ChatMessage {
  id: number
  from: 'user' | 'agent'
  text: string
  links?: ReadonlyArray<HelpLink>
  suggestions?: ReadonlyArray<string>
}

const WELCOME: ChatMessage = {
  id: 0,
  from: 'agent',
  text: WELCOME_TEXT,
  suggestions: STARTER_QUESTIONS,
}

const MAX_LENGTH = 300

/** **bold** inside a line. */
function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split('**').map((part, index) =>
        index % 2 === 1 ? (
          <strong key={index} className="font-semibold text-foreground">
            {part}
          </strong>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  )
}

/** Paragraphs split on a blank line; consecutive "• " lines become a list. */
function RichText({ text }: { text: string }) {
  const nodes: ReactNode[] = []
  for (const [blockIndex, block] of text.split('\n\n').entries()) {
    let bullets: string[] = []
    const flush = (key: string) => {
      if (bullets.length === 0) return
      const items = bullets
      bullets = []
      nodes.push(
        <ul key={key} className="space-y-1.5 pl-4">
          {items.map((item, i) => (
            <li key={i} className="list-disc marker:text-brand-blue-ink">
              <Inline text={item} />
            </li>
          ))}
        </ul>,
      )
    }
    for (const [lineIndex, line] of block.split('\n').entries()) {
      if (line.startsWith('• ')) {
        bullets.push(line.slice(2))
      } else if (line.trim()) {
        flush(`${blockIndex}-${lineIndex}-ul`)
        nodes.push(
          <p key={`${blockIndex}-${lineIndex}`}>
            <Inline text={line} />
          </p>,
        )
      }
    }
    flush(`${blockIndex}-end`)
  }
  return <div className="space-y-2.5">{nodes}</div>
}

/**
 * The site-only Help assistant (floating button on every page). It answers from the knowledge base
 * in `features/help` and politely declines anything that is not about BayFlow, so it can neither
 * wander off-topic nor invent features.
 */
export function HelpAgent() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME])
  const [draft, setDraft] = useState('')
  const [typing, setTyping] = useState(false)

  const nextId = useRef(1)
  const timer = useRef<number | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  // Keep the newest message in view.
  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages, typing, open])

  // Focus the question box when the panel opens.
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Never leave a reply timer running after unmount.
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  const ask = useCallback(
    (raw: string) => {
      const question = raw.trim().slice(0, MAX_LENGTH)
      if (!question || typing) return
      setMessages((prev) => [...prev, { id: nextId.current++, from: 'user', text: question }])
      setDraft('')
      setTyping(true)
      timer.current = window.setTimeout(
        () => {
          const reply = answerQuestion(question)
          setMessages((prev) => [
            ...prev,
            {
              id: nextId.current++,
              from: 'agent',
              text: reply.text,
              links: reply.links,
              suggestions: reply.suggestions,
            },
          ])
          setTyping(false)
          timer.current = null
        },
        380 + Math.min(question.length * 6, 420),
      )
    },
    [typing],
  )

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    ask(draft)
  }

  const close = () => {
    setOpen(false)
    launcherRef.current?.focus()
  }

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close()
    }
  }

  const reset = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    setTyping(false)
    setMessages([WELCOME])
    setDraft('')
    inputRef.current?.focus()
  }

  const lastAgentId = [...messages].reverse().find((m) => m.from === 'agent')?.id

  return (
    <div data-slot="help-agent" className="print:hidden">
      {open && (
        <section
          id={panelId}
          role="dialog"
          aria-label="BayFlow Help assistant"
          onKeyDown={onKeyDown}
          className="neu-surface fixed right-4 bottom-20 z-40 flex h-[min(34rem,calc(100dvh-7rem))] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-border/70 bg-card text-card-foreground sm:right-6 sm:bottom-24"
        >
          <header className="flex items-center gap-3 border-b border-border-faint bg-layer/60 px-4 py-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/30">
              <Bot className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="font-heading text-base leading-5 font-bold">BayFlow Help</h2>
              <p className="truncate text-xs text-helper">Ask me anything about this website</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Start a new conversation"
              title="New conversation"
              onClick={reset}
            >
              <RotateCcw aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              aria-label="Close help"
              onClick={close}
            >
              <X aria-hidden="true" />
            </Button>
          </header>

          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            aria-label="Conversation"
            className="flex-1 space-y-4 overflow-y-auto px-4 py-4"
          >
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn('flex flex-col gap-2', message.from === 'user' && 'items-end')}
              >
                <div
                  className={cn(
                    'max-w-[88%] px-3.5 py-2.5 text-sm leading-relaxed',
                    message.from === 'user'
                      ? 'rounded-2xl rounded-br-md bg-primary text-primary-foreground shadow-sm shadow-primary/25'
                      : 'rounded-2xl rounded-bl-md border border-border/60 bg-layer text-foreground',
                  )}
                >
                  {message.from === 'user' ? message.text : <RichText text={message.text} />}
                </div>

                {message.links && message.links.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {message.links.map((link) => (
                      <Button key={link.href + link.label} asChild size="xs" variant="default">
                        <Link href={link.href} onClick={() => setOpen(false)}>
                          {link.label}
                          <ArrowRight aria-hidden="true" />
                        </Link>
                      </Button>
                    ))}
                  </div>
                )}

                {message.id === lastAgentId &&
                  !typing &&
                  message.suggestions &&
                  message.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-2" role="group" aria-label="Suggested questions">
                      {message.suggestions.map((suggestion) => (
                        <Button
                          key={suggestion}
                          type="button"
                          variant="outline"
                          size="xs"
                          className="h-auto min-h-7 py-1.5 text-left whitespace-normal"
                          onClick={() => ask(suggestion)}
                        >
                          {suggestion}
                        </Button>
                      ))}
                    </div>
                  )}
              </div>
            ))}

            {typing && (
              <div
                className="flex w-fit items-center gap-1 rounded-2xl rounded-bl-md border border-border/60 bg-layer px-4 py-3"
                role="status"
                aria-label="BayFlow Help is typing"
              >
                {[0, 1, 2].map((dot) => (
                  <span
                    key={dot}
                    className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-[help-dot_1s_ease-in-out_infinite]"
                    style={{ animationDelay: `${dot * 150}ms` }}
                  />
                ))}
              </div>
            )}
          </div>

          <form onSubmit={onSubmit} className="border-t border-border-faint bg-layer/60 p-3">
            <div className="flex items-center gap-2">
              <label htmlFor={`${panelId}-q`} className="sr-only">
                Your question about BayFlow
              </label>
              <input
                id={`${panelId}-q`}
                ref={inputRef}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={MAX_LENGTH}
                autoComplete="off"
                placeholder="Ask about booking, estimates, roles…"
                className="neu-inset h-10.5 min-w-0 flex-1 rounded-full border border-input px-4 text-base text-foreground outline-none placeholder:text-helper focus-visible:border-brand-blue focus-visible:ring-4 focus-visible:ring-brand-blue/15 sm:text-sm"
              />
              <Button
                type="submit"
                size="icon"
                shape="square"
                aria-label="Send question"
                disabled={!draft.trim() || typing}
              >
                <Send aria-hidden="true" />
              </Button>
            </div>
            <p className="mt-2 px-1 text-center text-[11px] leading-4 text-helper">
              I only answer questions about BayFlow and this website.
            </p>
          </form>
        </section>
      )}

      <Button
        ref={launcherRef}
        type="button"
        size="lg"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={open ? 'Close help assistant' : 'Open help assistant'}
        onClick={() => (open ? close() : setOpen(true))}
        className="fixed right-4 bottom-4 z-40 sm:right-6 sm:bottom-6"
      >
        {open ? <X aria-hidden="true" /> : <MessageCircle aria-hidden="true" />}
        <span className="hidden sm:inline">{open ? 'Close' : 'Help'}</span>
      </Button>
    </div>
  )
}
