export default function LoadingSpinner({ size = 'md', text = 'Loading...' }) {
  const sizeClasses = {
    sm: 'w-5 h-5',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div
        className={`${sizeClasses[size]} border-4 border-dark-200 border-t-primary-600 rounded-full animate-spin`}
      />
      {text && <p className="text-sm text-dark-500">{text}</p>}
    </div>
  );
}
