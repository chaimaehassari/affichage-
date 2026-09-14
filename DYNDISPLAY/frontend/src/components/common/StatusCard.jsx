export default function StatusCard({ title, value, status, icon }) {
  return (
    <div className="bg-white rounded-lg border border-dark-200 p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-dark-500">{title}</p>
          <p className="text-2xl font-bold text-dark-900 mt-1">{value}</p>
        </div>
        {icon && (
          <div className="w-10 h-10 bg-primary-50 rounded-lg flex items-center justify-center">
            <svg
              className="w-5 h-5 text-primary-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={icon} />
            </svg>
          </div>
        )}
      </div>
      {status && (
        <div className="mt-3">
          <span
            className={`text-xs font-medium px-2 py-1 rounded-full ${
              status === 'healthy'
                ? 'bg-green-50 text-green-700'
                : status === 'warning'
                ? 'bg-yellow-50 text-yellow-700'
                : 'bg-red-50 text-red-700'
            }`}
          >
            {status}
          </span>
        </div>
      )}
    </div>
  );
}
