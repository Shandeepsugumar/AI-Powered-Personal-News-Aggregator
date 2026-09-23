import React, { useState, useEffect } from 'react';
import { X, KeyRound, Mail, User, Zap, ShieldCheck, Newspaper, AlertCircle, Loader2 } from 'lucide-react';

export default function AuthModal({ isOpen, onClose, onAuthSuccess, user }) {
  const [isRegister, setIsRegister] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const resetForm = () => {
    setName('');
    setEmail('');
    setPassword('');
    setError('');
  };

  // Reset form state whenever the modal opens or closes
  useEffect(() => {
    resetForm();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleQuickDemo = async () => {
    setError('');
    setIsLoading(true);
    const demoEmail = 'alex@example.com';
    const demoPassword = 'password123';
    const demoName = 'Alex';

    try {
      // 1. Try login first
      let response = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: demoEmail, password: demoPassword })
      });
      let data = await response.json();

      // 2. If login fails because user doesn't exist, auto-register demo user
      if (!response.ok) {
        response = await fetch(`${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: demoName, email: demoEmail, password: demoPassword })
        });
        data = await response.json();
      }

      if (!response.ok) {
        throw new Error(data.error || data.message || 'Quick demo login failed.');
      }

      localStorage.setItem('feedtoread_user', JSON.stringify(data));
      resetForm();
      onAuthSuccess(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const endpoint = isRegister ? `${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/auth/register` : `${import.meta.env.VITE_API_URL || `${import.meta.env.VITE_API_URL || "http://localhost:8000"}` + ""}/api/auth/login`;
    const body = isRegister 
      ? { name, email, password }
      : { email, password };

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || data.message || 'Authentication request failed');
      }

      localStorage.setItem('feedtoread_user', JSON.stringify(data));
      resetForm();
      onAuthSuccess(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/60 backdrop-blur-xs p-4">
      <div className="bg-[#FBF8F1] border-4 border-double border-stone-900 shadow-2xl max-w-md w-full p-6 sm:p-8 relative font-sans-ui text-stone-900">
        
        {/* Close Button */}
        <button 
          onClick={handleClose}
          className="absolute top-4 right-4 text-stone-500 hover:text-stone-900 p-1 border border-stone-300 hover:border-stone-900 transition-colors"
          aria-label="Close Auth Modal"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Press Card Header & Seal */}
        <div className="text-center border-b-2 border-stone-900 pb-4 mb-6">
          <div className="inline-flex items-center justify-center p-2 rounded-full border border-stone-900 mb-2 bg-stone-100">
            <Newspaper className="w-6 h-6 text-stone-900" />
          </div>
          <span className="block text-xs uppercase tracking-widest text-stone-600 font-serif font-bold mb-1">
            FeedToRead Editorial Press Bureau
          </span>
          <h2 className="text-2xl font-serif font-bold tracking-tight text-stone-900 uppercase">
            {isRegister ? "Claim Press Pass" : "Reader Subscription Desk"}
          </h2>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-300 text-red-800 text-xs font-serif flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
        )}

        {/* Quick Demo Bypass Button */}
        <button
          onClick={handleQuickDemo}
          disabled={isLoading}
          type="button"
          className="w-full mb-6 bg-stone-900 hover:bg-stone-800 text-[#FBF8F1] font-bold py-3 px-4 border-2 border-stone-900 flex items-center justify-center gap-2 shadow-md transition-all group cursor-pointer disabled:opacity-50"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin text-amber-400" />
          ) : (
            <Zap className="w-5 h-5 text-amber-400 group-hover:scale-110 transition-transform fill-amber-400" />
          )}
          <span className="tracking-wide">⚡ Quick Demo Sign-In (Skip Password)</span>
        </button>

        <div className="relative flex py-2 items-center mb-6">
          <div className="flex-grow border-t border-stone-300"></div>
          <span className="flex-shrink mx-4 text-stone-500 text-xs font-serif italic">or authenticate credential</span>
          <div className="flex-grow border-t border-stone-300"></div>
        </div>

        {/* Form Tabs */}
        <div className="flex border-b border-stone-400 mb-6">
          <button
            type="button"
            onClick={() => { setIsRegister(false); resetForm(); }}
            className={`flex-1 py-2 text-center text-sm font-semibold tracking-wider uppercase font-serif border-b-2 transition-all ${
              !isRegister ? "border-stone-900 text-stone-900 font-bold bg-stone-200/50" : "border-transparent text-stone-500 hover:text-stone-800"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setIsRegister(true); resetForm(); }}
            className={`flex-1 py-2 text-center text-sm font-semibold tracking-wider uppercase font-serif border-b-2 transition-all ${
              isRegister ? "border-stone-900 text-stone-900 font-bold bg-stone-200/50" : "border-transparent text-stone-500 hover:text-stone-800"
            }`}
          >
            Register Pass
          </button>
        </div>

        <form onSubmit={handleSubmit} autoComplete="off" className="space-y-4">
          {isRegister && (
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1">
                Full Name
              </label>
              <div className="relative">
                <User className="w-4 h-4 absolute left-3 top-3 text-stone-400" />
                <input
                  type="text"
                  required={isRegister}
                  placeholder="Alex Pressmember"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-[#FBF8F1] border border-stone-400 focus:border-stone-900 outline-none text-stone-900 text-sm"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1">
              Email Address
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 absolute left-3 top-3 text-stone-400" />
              <input
                type="email"
                required
                placeholder="alex@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-[#FBF8F1] border border-stone-400 focus:border-stone-900 outline-none text-stone-900 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-stone-700 mb-1">
              Password
            </label>
            <div className="relative">
              <KeyRound className="w-4 h-4 absolute left-3 top-3 text-stone-400" />
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                autoComplete={isRegister ? "new-password" : "current-password"}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-[#FBF8F1] border border-stone-400 focus:border-stone-900 outline-none text-stone-900 text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full mt-6 bg-stone-800 hover:bg-stone-900 text-[#FBF8F1] py-2.5 px-4 border border-stone-900 font-serif font-bold uppercase tracking-wider text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            <span>{isRegister ? "Issue New Press Credential" : "Authenticate & Open Pressroom"}</span>
          </button>
        </form>

        <div className="mt-6 text-center text-xs text-stone-500 font-serif border-t border-stone-200 pt-4 flex items-center justify-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5 text-stone-600" />
          <span>FeedToRead Encrypted Local Session · Branch feat/frontend-newspaper</span>
        </div>
      </div>
    </div>
  );
}
