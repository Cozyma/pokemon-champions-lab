#!/usr/bin/env node
/**
 * Extract AI-relevant move and ability data from Pokemon Showdown.
 *
 * Usage: node scripts/extract_showdown_data.js
 * Output: data/showdown-cache/moves.json, data/showdown-cache/abilities.json
 */
"use strict";

const path = require("path");
const fs = require("fs");

const SHOWDOWN_DIR = path.resolve(__dirname, "..", "engines", "showdown");
const OUTPUT_DIR = path.resolve(__dirname, "..", "data", "showdown-cache");

// Load Showdown's Dex with Champions mod
const { Dex } = require(path.join(SHOWDOWN_DIR, "dist", "sim"));
const dex = Dex.mod("champions");

// ---------------------------------------------------------------------------
// Moves
// ---------------------------------------------------------------------------
const moves = {};
for (const [id, move] of Object.entries(dex.data.Moves)) {
  if (move.isNonstandard && move.isNonstandard !== "Past") continue;

  const entry = {
    name: move.name,
    type: move.type,
    category: move.category,
    basePower: move.basePower || 0,
    accuracy: move.accuracy,
    pp: move.pp,
    priority: move.priority || 0,
    target: move.target,
  };

  // Flags
  if (move.flags) {
    if (move.flags.contact) entry.contact = true;
    if (move.flags.recharge) entry.recharge = true;
    if (move.flags.charge) entry.charge = true;
    if (move.flags.heal) entry.isHeal = true;
    if (move.flags.sound) entry.sound = true;
    if (move.flags.bullet) entry.bullet = true;
    if (move.flags.punch) entry.punch = true;
    if (move.flags.bite) entry.bite = true;
    if (move.flags.slicing) entry.slicing = true;
  }

  if (move.drain) entry.drain = move.drain;
  if (move.recoil) entry.recoil = move.recoil;
  if (move.selfdestruct) entry.selfdestruct = move.selfdestruct;
  if (move.boosts) entry.boosts = move.boosts;
  if (move.self && move.self.boosts) entry.selfBoosts = move.self.boosts;

  if (move.secondary) {
    const s = {};
    if (move.secondary.chance) s.chance = move.secondary.chance;
    if (move.secondary.boosts) s.boosts = move.secondary.boosts;
    if (move.secondary.status) s.status = move.secondary.status;
    if (move.secondary.volatileStatus) s.volatileStatus = move.secondary.volatileStatus;
    if (Object.keys(s).length > 0) entry.secondary = s;
  }
  if (move.secondaries) {
    const arr = move.secondaries
      .map((s) => {
        const o = {};
        if (s.chance) o.chance = s.chance;
        if (s.boosts) o.boosts = s.boosts;
        if (s.status) o.status = s.status;
        if (s.volatileStatus) o.volatileStatus = s.volatileStatus;
        return Object.keys(o).length > 0 ? o : null;
      })
      .filter(Boolean);
    if (arr.length > 0) entry.secondaries = arr;
  }

  if (move.multihit) entry.multihit = move.multihit;
  if (move.volatileStatus) entry.volatileStatus = move.volatileStatus;
  if (move.status) entry.status = move.status;
  if (move.sideCondition) entry.sideCondition = move.sideCondition;
  if (move.weather) entry.weather = move.weather;
  if (move.terrain) entry.terrain = move.terrain;
  if (move.forceSwitch) entry.forceSwitch = true;
  if (move.ohko) entry.ohko = true;
  if (move.critRatio) entry.critRatio = move.critRatio;
  if (move.willCrit) entry.willCrit = true;
  if (move.breaksProtect) entry.breaksProtect = true;
  if (move.hasCrashDamage) entry.hasCrashDamage = true;
  if (move.isZ) entry.isZ = true;
  if (move.isMax) entry.isMax = true;
  // Switch-in-only moves (Fake Out, First Impression)
  if (move.condition && move.condition.duration === 1) entry.switchInOnly = true;

  moves[id] = entry;
}

// ---------------------------------------------------------------------------
// Abilities
// ---------------------------------------------------------------------------
const abilities = {};
for (const [id, ability] of Object.entries(dex.data.Abilities)) {
  if (ability.isNonstandard && ability.isNonstandard !== "Past") continue;

  const entry = {
    name: ability.name,
    rating: ability.rating || 0,
  };

  // Detect AI-relevant callbacks from the ability object
  const flags = [];
  const src = JSON.stringify(ability);

  if (src.includes("onModifyAtk")) flags.push("modifyAtk");
  if (src.includes("onModifySpA")) flags.push("modifySpA");
  if (src.includes("onModifyDef")) flags.push("modifyDef");
  if (src.includes("onModifySpD")) flags.push("modifySpD");
  if (src.includes("onModifySpe")) flags.push("modifySpe");
  if (src.includes("onDamagingHit")) flags.push("contactPunish");
  if (src.includes("onSourceModifyDamage")) flags.push("reduceIncoming");
  if (src.includes("onTryHit")) flags.push("tryHitBlock");
  if (src.includes("onModifySTAB")) flags.push("modifySTAB");
  if (src.includes("onModifyType")) flags.push("modifyType");
  if (src.includes("onBasePower") || src.includes("onModifyDamage")) flags.push("modifyPower");
  if (src.includes("onImmunity")) flags.push("immunity");
  if (src.includes("onModifyAccuracy") || src.includes("onSourceModifyAccuracy")) flags.push("modifyAccuracy");
  if (src.includes("onAnyModifyBoost")) flags.push("modifyBoost");
  if (src.includes("onResidual")) flags.push("residual");

  if (flags.length > 0) entry.flags = flags;

  abilities[id] = entry;
}

// ---------------------------------------------------------------------------
// Pokedex (species -> types, abilities, baseStats)
// ---------------------------------------------------------------------------
const pokedex = {};
for (const [id, species] of Object.entries(dex.data.Pokedex)) {
  if (species.isNonstandard && species.isNonstandard !== "Past") continue;
  if (species.num <= 0) continue;

  const entry = {
    name: species.name,
    types: species.types,
    baseStats: species.baseStats,
    abilities: {},
  };
  for (const [slot, abilityName] of Object.entries(species.abilities || {})) {
    const ab = dex.abilities.get(abilityName);
    entry.abilities[slot] = ab ? ab.id : abilityName.toLowerCase().replace(/\s/g, "");
  }

  pokedex[id] = entry;
}

// ---------------------------------------------------------------------------
// Write output
// ---------------------------------------------------------------------------
fs.mkdirSync(OUTPUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUTPUT_DIR, "moves.json"), JSON.stringify(moves, null, 2));
fs.writeFileSync(path.join(OUTPUT_DIR, "abilities.json"), JSON.stringify(abilities, null, 2));

fs.writeFileSync(path.join(OUTPUT_DIR, "pokedex.json"), JSON.stringify(pokedex, null, 2));
console.log(`Extracted ${Object.keys(moves).length} moves -> data/showdown-cache/moves.json`);
console.log(`Extracted ${Object.keys(abilities).length} abilities -> data/showdown-cache/abilities.json`);
console.log(`Extracted ${Object.keys(pokedex).length} species -> data/showdown-cache/pokedex.json`);
