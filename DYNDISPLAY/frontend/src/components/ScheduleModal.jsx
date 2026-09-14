import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

const DAY_LABELS = [
  { key: 'MON', label: 'Lun' },
  { key: 'TUE', label: 'Mar' },
  { key: 'WED', label: 'Mer' },
  { key: 'THU', label: 'Jeu' },
  { key: 'FRI', label: 'Ven' },
  { key: 'SAT', label: 'Sam' },
  { key: 'SUN', label: 'Dim' },
];

export default function ScheduleModal({ schedule, onSave, onClose }) {
  const [form, setForm] = useState({
    name: '',
    start_date: '',
    end_date: '',
    start_time: '',
    end_time: '',
    days_of_week: [],
    is_active: true,
  });

  useEffect(() => {
    if (schedule) {
      const days = schedule.days_of_week ? schedule.days_of_week.split(',') : [];
      setForm({
        name: schedule.name || '',
        start_date: schedule.start_date || '',
        end_date: schedule.end_date || '',
        start_time: schedule.start_time ? schedule.start_time.substring(0, 5) : '',
        end_time: schedule.end_time ? schedule.end_time.substring(0, 5) : '',
        days_of_week: days,
        is_active: schedule.is_active ?? true,
      });
    }
  }, [schedule]);

  function toggleDay(day) {
    setForm(prev => ({
      ...prev,
      days_of_week: prev.days_of_week.includes(day)
        ? prev.days_of_week.filter(d => d !== day)
        : [...prev.days_of_week, day],
    }));
  }

  function handleSubmit() {
    if (!form.name.trim()) return;
    onSave({
      name: form.name.trim(),
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      start_time: form.start_time || null,
      end_time: form.end_time || null,
      days_of_week: form.days_of_week.length > 0 ? form.days_of_week.join(',') : null,
      is_active: form.is_active,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-[480px] shadow-2xl max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold text-sm">
            {schedule?.schedule_id ? 'Modifier le planning' : 'Nouveau planning'}
          </h3>
          <button onClick={onClose} className="text-[#a0a7b3] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-[#a0a7b3] text-xs mb-1">Nom</label>
            <input type="text" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
              placeholder="Ex: Planning journée"
              className="w-full bg-[#111418] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[#a0a7b3] text-xs mb-1">Date de début</label>
              <input type="date" value={form.start_date} onChange={e => setForm(p => ({ ...p, start_date: e.target.value }))}
                className="w-full bg-[#111418] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none" />
            </div>
            <div>
              <label className="block text-[#a0a7b3] text-xs mb-1">Date de fin</label>
              <input type="date" value={form.end_date} onChange={e => setForm(p => ({ ...p, end_date: e.target.value }))}
                className="w-full bg-[#111418] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[#a0a7b3] text-xs mb-1">Heure de début</label>
              <input type="time" value={form.start_time} onChange={e => setForm(p => ({ ...p, start_time: e.target.value }))}
                className="w-full bg-[#111418] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none" />
            </div>
            <div>
              <label className="block text-[#a0a7b3] text-xs mb-1">Heure de fin</label>
              <input type="time" value={form.end_time} onChange={e => setForm(p => ({ ...p, end_time: e.target.value }))}
                className="w-full bg-[#111418] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="block text-[#a0a7b3] text-xs mb-2">Jours de la semaine</label>
            <div className="flex gap-2">
              {DAY_LABELS.map(d => (
                <button key={d.key} onClick={() => toggleDay(d.key)}
                  className={`px-3 py-1.5 text-xs rounded border transition-colors ${form.days_of_week.includes(d.key) ? 'bg-[#f6c200]/20 border-[#f6c200]/40 text-[#f6c200]' : 'bg-[#111418] border-white/10 text-[#a0a7b3] hover:text-white'}`}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" checked={form.is_active} onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))}
              className="w-4 h-4 rounded border-white/20 bg-[#111418] text-[#f6c200] focus:ring-[#f6c200]" />
            <span className="text-sm text-white">Actif</span>
          </div>
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onClose} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
            Annuler
          </button>
          <button onClick={handleSubmit} disabled={!form.name.trim()}
            className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-40"
            style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
            <span className="text-[#111418]">{schedule?.schedule_id ? 'Mettre à jour' : 'Créer'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
