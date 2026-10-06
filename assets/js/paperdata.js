// All numbers transcribed from the PhySimCode paper (main text + appendix).
window.PAPER = (() => {
  const M = {
    claude_fable_5_1:      { name: 'Claude Fable 5.1',      group: 'frontier', color: '#d9480f' },
    gpt_6_astra:           { name: 'GPT-6 Astra',           group: 'frontier', color: '#0b7285' },
    grok_4_6:              { name: 'Grok 4.6',              group: 'frontier', color: '#495057' },
    kimi_k3:               { name: 'Kimi K3',               group: 'frontier', color: '#9c36b5' },
    gpt_5_mini:            { name: 'GPT-5 Mini',            group: 'closed',   color: '#10a37f' },
    gemini_2_5_pro:        { name: 'Gemini 2.5 Pro',        group: 'closed',   color: '#4263eb' },
    claude_sonnet_4_6:     { name: 'Claude Sonnet 4.6',     group: 'closed',   color: '#e8590c' },
    grok_4_fast_reasoning: { name: 'Grok 4 Fast Reasoning', group: 'closed',   color: '#868e96' },
    nova_2_lite:           { name: 'Nova 2 Lite',           group: 'closed',   color: '#f59f00' },
    qwen3vl_30b_a3b:       { name: 'Qwen3-VL-30B-A3B',      group: 'open',     color: '#7048e8' },
    internvl3_5_30b_a3b:   { name: 'InternVL3.5-30B-A3B',   group: 'open',     color: '#1c7ed6' },
    gemma_3_12b_it:        { name: 'Gemma-3-12B-IT',        group: 'open',     color: '#2b8a3e' },
    glm_4_1v_9b_thinking:  { name: 'GLM-4.1V-9B-Thinking',  group: 'open',     color: '#c2255c' },
    pixtral_12b:           { name: 'Pixtral-12B',           group: 'open',     color: '#f76707' },
  };
  const MAIN = ['gpt_5_mini','gemini_2_5_pro','claude_sonnet_4_6','grok_4_fast_reasoning','nova_2_lite',
                'qwen3vl_30b_a3b','internvl3_5_30b_a3b','gemma_3_12b_it','glm_4_1v_9b_thinking','pixtral_12b'];
  const FRONTIER = ['claude_fable_5_1','gpt_6_astra','grok_4_6','kimi_k3'];

  // Table 3: [correctness formula, correctness overall, eq name, eq statement, eq formula, eq overall]
  const T3 = {
    qwen3vl_30b_a3b: [4.58,4.68,2.18,2.09,1.92,2.02], internvl3_5_30b_a3b: [4.68,4.64,1.98,1.96,1.75,1.82],
    gemma_3_12b_it: [4.90,4.93,2.15,1.95,1.72,1.90], glm_4_1v_9b_thinking: [4.46,4.43,2.14,2.03,1.80,1.91],
    pixtral_12b: [4.43,4.50,1.70,1.57,1.45,1.51], gpt_5_mini: [4.75,4.70,2.71,2.69,2.24,2.47],
    gemini_2_5_pro: [4.76,4.66,2.49,2.48,2.16,2.34], claude_sonnet_4_6: [4.53,4.33,2.58,2.45,2.09,2.26],
    grok_4_fast_reasoning: [4.65,4.58,2.16,2.16,1.85,1.98], nova_2_lite: [4.29,4.27,1.80,1.87,1.59,1.69],
  };
  // Table 4: [phys plausibility, physics eq, appearance eq, DINOv2, VideoCLIP]
  const T4 = {
    qwen3vl_30b_a3b: [3.16,1.88,2.31,0.557,0.713], internvl3_5_30b_a3b: [1.43,1.23,1.59,0.482,0.667],
    gemma_3_12b_it: [2.64,1.80,2.56,0.447,0.643], glm_4_1v_9b_thinking: [2.43,1.32,2.04,0.551,0.732],
    pixtral_12b: [1.48,1.13,1.26,0.448,0.638], gpt_5_mini: [3.40,2.40,2.66,0.672,0.785],
    gemini_2_5_pro: [3.96,2.86,3.45,0.774,0.838], claude_sonnet_4_6: [3.30,2.30,3.14,0.767,0.837],
    grok_4_fast_reasoning: [1.90,1.65,2.28,0.629,0.750], nova_2_lite: [2.62,1.14,1.63,0.480,0.687],
  };
  // Table 5: [param acc %, CoT, Code, Compile, No errors, Video save, CodeBLEU]
  const T5 = {
    qwen3vl_30b_a3b: [6.16,99.8,96.8,96.6,73.8,77.9,0.206], internvl3_5_30b_a3b: [3.52,99.8,99.7,94.0,48.0,62.5,0.195],
    gemma_3_12b_it: [3.98,99.0,95.4,95.2,39.6,47.7,0.200], glm_4_1v_9b_thinking: [4.84,96.6,87.6,87.4,46.6,48.0,0.198],
    pixtral_12b: [3.31,99.8,99.7,99.0,42.6,60.7,0.187], gpt_5_mini: [7.13,83.7,98.6,98.2,92.8,93.3,0.241],
    gemini_2_5_pro: [6.06,96.1,66.2,66.1,58.7,59.2,0.223], claude_sonnet_4_6: [7.69,100.0,99.9,99.8,98.8,99.0,0.232],
    grok_4_fast_reasoning: [5.69,98.9,100.0,99.6,89.4,90.4,0.209], nova_2_lite: [3.76,97.0,99.0,98.5,75.9,78.7,0.204],
  };
  // Table 9: [parse fails, avg pred params, avg matched, naming recall, value acc (mean), global acc, end-to-end]
  const T9 = {
    claude_sonnet_4_6: [0,7.7,3.29,0.460,0.171,0.185,0.0769], gemini_2_5_pro: [96,5.5,2.83,0.399,0.150,0.170,0.0606],
    gemma_3_12b_it: [330,4.8,1.94,0.281,0.130,0.163,0.0398], glm_4_1v_9b_thinking: [420,4.0,1.93,0.273,0.147,0.199,0.0484],
    gpt_5_mini: [465,8.4,3.17,0.426,0.139,0.178,0.0713], grok_4_fast_reasoning: [32,5.9,2.74,0.389,0.155,0.165,0.0569],
    internvl3_5_30b_a3b: [22,3.7,1.77,0.259,0.141,0.158,0.0352], nova_2_lite: [203,4.0,1.78,0.258,0.136,0.167,0.0376],
    pixtral_12b: [365,3.5,1.39,0.198,0.134,0.188,0.0331], qwen3vl_30b_a3b: [29,6.2,2.80,0.407,0.158,0.174,0.0616],
  };
  // Tables 6 / 7 / 8 (10 hard samples)
  const T6 = {
    claude_fable_5_1: [4.40,4.33,3.47,3.13,2.90,3.00], gpt_6_astra: [4.73,4.50,3.27,2.87,2.63,2.80],
    grok_4_6: [4.40,4.23,2.87,2.53,2.30,2.40], kimi_k3: [4.40,4.37,3.57,2.63,2.40,2.67],
    qwen3vl_30b_a3b: [4.73,4.87,1.83,1.67,1.50,1.60], internvl3_5_30b_a3b: [4.53,4.53,1.47,1.73,1.17,1.40],
    gemma_3_12b_it: [5.00,5.00,2.10,1.87,1.43,1.73], glm_4_1v_9b_thinking: [4.50,4.60,1.90,1.90,1.70,1.80],
    pixtral_12b: [4.63,4.63,1.80,1.50,1.83,1.53], gpt_5_mini: [4.87,4.60,1.87,2.07,1.53,1.60],
    gemini_2_5_pro: [4.19,4.30,2.07,1.85,1.74,1.96], claude_sonnet_4_6: [3.73,3.50,2.17,2.10,1.43,1.77],
    grok_4_fast_reasoning: [4.77,4.53,2.03,2.10,1.70,1.93], nova_2_lite: [4.80,4.63,2.10,1.93,1.70,1.80],
  };
  const T7 = {
    claude_fable_5_1: [0.855,0.881], gpt_6_astra: [0.902,0.896], grok_4_6: [0.781,0.869], kimi_k3: [0.863,0.903],
    qwen3vl_30b_a3b: [0.506,0.716], internvl3_5_30b_a3b: [0.580,0.733], gemma_3_12b_it: [0.595,0.609],
    glm_4_1v_9b_thinking: [0.576,0.740], pixtral_12b: [0.339,0.669], gpt_5_mini: [0.714,0.812],
    gemini_2_5_pro: [0.788,0.843], claude_sonnet_4_6: [0.802,0.841], grok_4_fast_reasoning: [0.625,0.768], nova_2_lite: [0.428,0.666],
  };
  const T8 = {
    claude_fable_5_1: [18.18,100,100,100,100,100,0.240], gpt_6_astra: [5.19,100,100,100,100,100,0.240],
    grok_4_6: [9.09,100,100,100,100,100,0.237], kimi_k3: [12.99,100,100,100,100,100,0.244],
    qwen3vl_30b_a3b: [3.90,100,100,100,80,80,0.202], internvl3_5_30b_a3b: [3.90,100,90,60,10,10,0.184],
    gemma_3_12b_it: [3.90,100,100,100,10,10,0.193], glm_4_1v_9b_thinking: [3.90,100,70,70,30,30,0.189],
    pixtral_12b: [3.90,100,100,100,50,60,0.179], gpt_5_mini: [3.90,50,90,90,80,80,0.245],
    gemini_2_5_pro: [5.19,90,60,60,60,60,0.199], claude_sonnet_4_6: [5.19,100,90,90,90,90,0.232],
    grok_4_fast_reasoning: [6.49,100,100,100,90,90,0.196], nova_2_lite: [2.60,100,100,100,70,80,0.195],
  };
  // Table 10: authorship-bias (difference-in-differences) scores
  const T10 = [
    ['Law equivalence – Overall', 0.27, 0.30, ''], ['Law validity – Overall', 0.02, -0.04, ''],
    ['CodeBLEU', 0.000, -0.003, ''], ['Runs without error', -3.2, -3.9, 'pp'],
    ['Video save', -2.2, -1.6, 'pp'], ['Param. Est. Acc. (±20%)', 0.76, -1.93, 'pp'],
  ];
  // Table 13: Spearman rank agreement between Claude- and GPT-authored arms
  const T13 = [
    ['CodeBLEU',1.000,'~0'],['Law validity – Statement',0.976,'~0'],['Runs without error',0.976,'~0'],
    ['Law validity – Name',0.952,'~0'],['Law validity – Overall',0.905,'0.002'],['Video save',0.905,'0.002'],
    ['Param. Est. Acc. (±20%)',0.786,'0.021'],['Law equivalence – Formula',0.762,'0.028'],
    ['Law equivalence – Statement',0.667,'0.071'],['Law equivalence – Overall',0.643,'0.086'],
    ['Syntax OK',0.643,'0.086'],['Law validity – Formula',0.500,'0.207'],['Law equivalence – Name',0.357,'0.385'],
  ];
  // Table 20: frame-count ablation
  const T20 = {
    frames: { qwen: [8,16,32,60,80], internvl: [8,16,32,60] },
    paper: { qwen: 60, internvl: 32 },
    param: { qwen: [5.84,6.23,6.31,6.07,5.76], internvl: [3.12,3.43,4.05,4.28] },
    recall: { qwen: [0.384,0.387,0.399,0.409,0.408], internvl: [0.247,0.256,0.265,0.273] },
    value: { qwen: [0.155,0.165,0.168,0.157,0.143], internvl: [0.126,0.132,0.163,0.168] },
    noerr: { qwen: [78.4,75.3,71.0,75.3,77.8], internvl: [48.1,49.4,50.6,46.3] },
  };
  // Figure 4 / 6 weighted Cohen's kappa
  const KAPPA = {
    physics: { closed: { 'Human–DINOv2': 0.198, 'Human–VideoCLIP': 0.205, 'DINOv2–VideoCLIP': 0.717 },
               open:   { 'Human–DINOv2': 0.012, 'Human–VideoCLIP': -0.035, 'DINOv2–VideoCLIP': 0.439 } },
    appearance: { closed: { 'Human–DINOv2': 0.376, 'Human–VideoCLIP': 0.356, 'DINOv2–VideoCLIP': 0.717 },
                  open:   { 'Human–DINOv2': 0.176, 'Human–VideoCLIP': 0.176, 'DINOv2–VideoCLIP': 0.439 } },
    judges: { closed: { 'Gemini-2.5-Flash – GPT-5-Nano': 0.696, 'Grok-4.1-Fast – GPT-5-Nano': 0.815, 'Grok-4.1-Fast – Gemini-2.5-Flash': 0.785 },
              open:   { 'Gemini-2.5-Flash – GPT-5-Nano': 0.488, 'Grok-4.1-Fast – GPT-5-Nano': 0.699, 'Grok-4.1-Fast – Gemini-2.5-Flash': 0.716 } },
  };
  const DOMAINS = {
    'Rigid Body': { n: 35, color: '#e8707a' }, 'Spring / Wave': { n: 29, color: '#38b2a0' },
    'Articulated': { n: 24, color: '#f08c3c' }, 'Constrained': { n: 18, color: '#d9b310' },
    'Pendulum': { n: 17, color: '#74b84a' }, 'Real-life Mixed': { n: 14, color: '#8c7ae6' },
    'Rolling': { n: 12, color: '#4a9be0' }, 'Rope / Granular': { n: 8, color: '#d66fb0' },
    'Gravitation / Fluid': { n: 5, color: '#b08d64' },
  };
  const LAWS = [['Newton II (translational)',162],['Newton II (rotational)',62],['Conservation of energy',42],
    ['Conservation of momentum',38],["Hooke's law",30],['Lagrangian mechanics',28],['Coulomb friction',27],
    ['Holonomic constraints',24],['Other',9],['Wave equation',7]];
  // Table 1
  const PRIOR = [
    ['Physion',1,0,0,0,0,0,0,'8','~24K'],['IntPhys',1,0,0,0,0,0,0,'–','15K'],['CLEVRER',1,1,0,0,0,0,0,'–','20K'],
    ['ComPhy',1,1,0,0,0,0,0,'–','~100K'],['ContPhy',1,1,0,0,0,0,0,'–','6.5K'],['PHYBench',0,1,0,0,1,0,0,'–','500'],
    ['PhysBench',1,1,0,0,0,0,0,'–','10,002'],['VideoPhy',0,1,0,0,0,0,0,'–','11,330'],['VBench',1,1,0,0,0,0,0,'8','≥800'],
    ['Morpheus',1,1,0,0,1,0,0,'9','130'],['PhysInOne',1,1,0,0,0,1,0,'71','2M'],['PhysCodeBench',0,1,0,1,1,0,0,'–','700'],
    ['SimuScene',0,1,1,1,1,0,0,'52','7,659'],['PhysVid',1,0,0,0,0,0,0,'–','12.1K'],
    ['PhySimCode (Ours)',1,1,1,1,1,1,1,'162','160.7K'],
  ];
  return { M, MAIN, FRONTIER, T3, T4, T5, T9, T6, T7, T8, T10, T13, T20, KAPPA, DOMAINS, LAWS, PRIOR };
})();
