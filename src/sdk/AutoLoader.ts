export class BaseAutoloader {
    protected _enabled = false;
    protected _directory = "";
    protected _recursive = true;

    /**
     * Enables or disables this autoloader.
     */
    setEnabled(enabled: boolean): this {
        this._enabled = enabled;
        return this;
    }

    /**
     * Sets the directory to scan.
     */
    setDirectory(directory: string): this {
        this._directory = directory;
        return this;
    }

    /**
     * Enables or disables recursive scanning.
     */
    setRecursive(recursive: boolean): this {
        this._recursive = recursive;
        return this;
    }

    get enabled(): boolean {
        return this._enabled;
    }

    get directory(): string {
        return this._directory;
    }

    get isRecursive(): boolean {
        return this._recursive;
    }
}

export class CommandAutoloader<T = any, R = any> extends BaseAutoloader {
    protected _mapping?: (file: T) => R;

    setMapper(mapping: (file: T) => R): this {
        this._mapping = mapping;
        return this;
    }

    get mapping(): ((file: T) => R) | undefined {
        return this._mapping;
    }
}

export class EventAutoloader extends BaseAutoloader {
    protected _mapping?: (file: T) => R;

    setMapper(mapping: (file: T) => R): this {
        this._mapping = mapping;
        return this;
    }

    get mapping(): ((file: T) => R) | undefined {
        return this._mapping;
    }
}

export class ModuleAutoloader extends BaseAutoloader {}

export class ServiceAutoloader extends BaseAutoloader {}

export class ListenerAutoloader extends BaseAutoloader {}

export default class Autoloader {
    readonly commands = new CommandAutoloader();
    readonly events = new EventAutoloader();
    readonly modules = new ModuleAutoloader();
    readonly services = new ServiceAutoloader();
    readonly listeners = new ListenerAutoloader();
}