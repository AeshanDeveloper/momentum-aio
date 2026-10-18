import logger from "@core/logging/Logger";

function errorHandler(err: any, req: any, res: any, _next: any) {
  if (err.statusCode !== 404) {
    logger.error('Unhandled error occurred', {
      error: err.message,
      stack: err.stack,
      url: req.url,
      method: req.method,
      ip: req.ip,
      userAgent: req.get('User-Agent')
    });
  }
  // Determine status code
  const statusCode = err.statusCode || err.status || 500;
  
  // Format error response
  const errorResponse = {
    success: false,
    error: {
      message: statusCode === 500 ? 'Internal Server Error' : err.message,
      ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
    }
  };

  // Send JSON response for API requests
  if (req.originalUrl.startsWith('/api')) {
    return res.status(statusCode).json(errorResponse);
  }

  // Render error page for other requests
  res.status(statusCode).render('error', {
    status: statusCode,
    message: errorResponse.error.message,
    error: errorResponse
  });
}

export default errorHandler;
