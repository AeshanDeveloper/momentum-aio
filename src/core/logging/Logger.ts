import winston, { format, transports } from "winston";
import "winston-daily-rotate-file";

const { combine, timestamp, printf, colorize, errors, splat } = format;

const logFormat = printf(({ level, message, timestamp, stack, [Symbol.for("splat")]: extraSplat }) => {
    let msg = stack ?? message;
    if (extraSplat && Array.isArray(extraSplat) && extraSplat.length > 0) {
        const extra = extraSplat
            .map((x) => (x instanceof Error ? x.stack || x.message : typeof x === "object" ? JSON.stringify(x) : String(x)))
            .join(" ");
        msg = `${msg} ${extra}`;
    }
    return `${timestamp} ${level}: ${msg}`;
});

const logger = winston.createLogger({
    level: process.env.LOG_LEVEL ?? "info",

    format: combine(
        errors({ stack: true }),
        splat(),
        timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
        logFormat
    ),

    transports: [
        new transports.Console({
            format: combine(
                colorize(),
                errors({ stack: true }),
                splat(),
                timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
                logFormat
            )
        }),

        new transports.DailyRotateFile({
            filename: "logs/combined-%DATE%.log",
            datePattern: "YYYY-MM-DD",
            maxFiles: "14d",
            format: combine(
                errors({ stack: true }),
                timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
                logFormat
            )
        }),

        new transports.DailyRotateFile({
            level: "error",
            filename: "logs/error-%DATE%.log",
            datePattern: "YYYY-MM-DD",
            maxFiles: "30d",
            format: combine(
                errors({ stack: true }),
                timestamp({ format: "YYYY-MM-DD HH:mm:ss" }),
                logFormat
            )
        })
    ]
});

export default logger;