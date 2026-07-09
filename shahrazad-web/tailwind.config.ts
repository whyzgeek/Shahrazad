import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        shahrazad: {
          ink: "#1a1209",
          gold: "#c9a227",
          sand: "#f5efe6",
          dusk: "#3d2c1e",
        },
      },
      fontFamily: {
        arabic: ["Noto Naskh Arabic", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
