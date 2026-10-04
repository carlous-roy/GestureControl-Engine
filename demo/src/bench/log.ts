// The bench's log: the host's lines as the Python logger would print them, and the strings the
// firmware sends with Firmata.sendString, in one pane.

export type LogLevel = 'INFO' | 'WARN' | 'ERROR'
export type LogSource = 'host' | 'board' | 'bench'

export interface LogLine {
  seq: number
  /** Bench time in milliseconds. */
  t: number
  source: LogSource
  level: LogLevel
  message: string
}

export const LOG_LIMIT = 400

export class BenchLog {
  private lines: LogLine[] = []
  private nextSeq = 1
  private view: LogLine[] | null = null
  /** A clock the log reads so callers do not pass the time on every line. */
  now: () => number

  constructor(now: () => number) {
    this.now = now
  }

  get revision(): number {
    return this.nextSeq - 1
  }

  write(source: LogSource, level: LogLevel, message: string): void {
    this.lines.push(Object.freeze({ seq: this.nextSeq++, t: this.now(), source, level, message }))
    if (this.lines.length > LOG_LIMIT * 2) this.lines = this.lines.slice(-LOG_LIMIT)
    this.view = null
  }

  info(source: LogSource, message: string): void {
    this.write(source, 'INFO', message)
  }

  warn(source: LogSource, message: string): void {
    this.write(source, 'WARN', message)
  }

  error(source: LogSource, message: string): void {
    this.write(source, 'ERROR', message)
  }

  /** The newest lines, the same array while nothing was written. */
  snapshot(): LogLine[] {
    if (this.view === null) this.view = this.lines.slice(-LOG_LIMIT)
    return this.view
  }

  clear(): void {
    this.lines = []
    this.view = null
  }
}
