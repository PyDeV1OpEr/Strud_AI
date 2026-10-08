// Strud brand mark — a compact leaf/helix hybrid. No emoji, custom identity.

export function StrudLogo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <rect
        x="1.5"
        y="1.5"
        width="29"
        height="29"
        rx="9"
        fill="rgba(255,255,255,0.05)"
        stroke="rgba(255,255,255,0.14)"
      />
      {/* leaf blade */}
      <path
        d="M10 21C10 14 15 10 22 10C22 17 17 21 10 21Z"
        fill="url(#strud-leaf)"
      />
      {/* helix rung */}
      <path
        d="M13 18C16 16.5 18.5 15.5 21 15"
        stroke="rgba(7,7,8,0.85)"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <defs>
        <linearGradient id="strud-leaf" x1="10" y1="10" x2="22" y2="21">
          <stop stopColor="#6ee7b7" />
          <stop offset="1" stopColor="#34d399" />
        </linearGradient>
      </defs>
    </svg>
  );
}
