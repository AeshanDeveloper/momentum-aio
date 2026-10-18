import { EventEmitter } from "node:events";
import type { EventMap, EventPayload } from "@shared/types/EventMap";
import { randomUUID } from "node:crypto";

export default class Events {
    private readonly emitter = new EventEmitter();

    constructor() {
		runtime.modules.loaded++;
		runtime.modules.total++;
        this.emitter.setMaxListeners(0);
    }

    publish<E extends keyof EventMap>(
        event: E,
        payload: EventMap[E]
    ): boolean {
        return this.emitter.emit(String(event), {
            event,
			eventId: randomUUID(),
            timestamp: Date.now(),
            ...payload,
        } satisfies EventPayload<E>);
    }

    subscribe<E extends keyof EventMap>(
        event: E,
        listener: (payload: EventPayload<E>) => void
    ): this {
        this.emitter.on(String(event), listener);
        return this;
    }

    once<E extends keyof EventMap>(
        event: E,
        listener: (payload: EventPayload<E>) => void
    ): this {
        this.emitter.once(String(event), listener);
        return this;
    }

    off<E extends keyof EventMap>(
        event: E,
        listener: (payload: EventPayload<E>) => void
    ): this {
        this.emitter.off(String(event), listener);
        return this;
    }

    removeAllListeners(event?: keyof EventMap): this {
        this.emitter.removeAllListeners(event === undefined ? undefined : String(event));
        return this;
    }

    listenerCount(event: keyof EventMap): number {
        return this.emitter.listenerCount(String(event));
    }

    listeners<E extends keyof EventMap>(
        event: E
    ): Array<(payload: EventPayload<E>) => void> {
        return this.emitter.listeners(String(event)) as Array<
            (payload: EventPayload<E>) => void
        >;
    }
}
