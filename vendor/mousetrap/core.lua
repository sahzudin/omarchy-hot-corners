local M = {}

local path = (...):gsub("%.core$", "")

local Geometry = require(path .. ".geometry")
local Bindings = require(path .. ".bindings")
local Trigger = require(path .. ".trigger")
local Events = require(path .. ".events")

local get_cursor = hl.get_cursor_pos
local get_monitor = hl.get_monitor_at_cursor
local create_timer = hl.timer

local EMPTY_GEOM = {}

local context = nil

local function reset_position(state)
	state.last_x = nil
	state.last_y = nil
end

local function get_geometry(config, monitor)
	if not config or not config.geometry then
		return EMPTY_GEOM
	end

	return config.geometry[monitor.name] or config.geometry.default or EMPTY_GEOM
end

local function same_monitor(a, b)
	return a and b and a.name == b.name
end

local function same_bindings(a, b)
	if a == b then
		return true
	end

	if not a or not b then
		return false
	end

	if #a ~= #b then
		return false
	end

	for index = 1, #a do
		if a[index] ~= b[index] then
			return false
		end
	end

	return true
end

local function tick()
	local state = context.state
	local config = context.config

	if not config then
		return
	end

	local cursor = get_cursor()

	if not cursor then
		return
	end

	local monitor = get_monitor()

	if not monitor then
		return
	end

	local geometry = get_geometry(config, monitor)

	local x = cursor.x - monitor.x
	local y = cursor.y - monitor.y

	local zone = Geometry.get_zone_at_pos(x, y, monitor, geometry)

	local bindings = Bindings.get_bindings(zone)

	if zone ~= state.zone then
		local exit_binding = Bindings.get_exit_binding(state.zone)

		if exit_binding then
			Trigger.exit(state, state.zone, exit_binding, zone, monitor)
		end
	end

	if
		zone ~= state.zone
		or not same_monitor(state.monitor, monitor)
		or not same_bindings(state.active_bindings, bindings)
	then
		Trigger.reset(state, zone, monitor, bindings)
	end

	Trigger.update(state, x, y, monitor, bindings)

	state.last_x = x
	state.last_y = y
end

function M.init(ctx)
	context = ctx

	Bindings.init(ctx)
	Events.init(ctx)
	context.events = Events

	local config = ctx.config
	local state = ctx.state

	state.timer_interval = config.motion and config.motion.timer or 16

	if config.motion and config.motion.zone_direction then
		state.motion.cardinal = config.motion.zone_direction.cardinal or 5
		state.motion.diagonal = config.motion.zone_direction.diagonal or 3
	end
end

function M.reload(ctx)
	context = ctx

	Bindings.reload(ctx)

	local config = ctx.config
	local state = ctx.state

	state.timer_interval = config.motion and config.motion.timer or 16
	if config.motion and config.motion.zone_direction then
		state.motion.cardinal = config.motion.zone_direction.cardinal or 5
		state.motion.diagonal = config.motion.zone_direction.diagonal or 3
	end
end

function M.set_modifiers(modifiers)
	Bindings.set_modifiers(modifiers)
end

function M.start()
	local state = context.state

	if not state.runtime.timer then
		state.runtime.timer = create_timer(tick, {
			type = "repeat",
			timeout = state.timer_interval,
		})
	else
		state.runtime.timer:set_enabled(true)
	end

	state.runtime.running = true

	reset_position(state)
end

function M.stop()
	local state = context.state

	if state.runtime.timer then
		state.runtime.timer:set_enabled(false)
	end

	state.runtime.running = false

	state.zone = "none"
	state.monitor = nil

	state.active_bindings = nil

	state.time = 0
	state.triggered = false

	state.direction_x = 0
	state.direction_y = 0

	reset_position(state)
end

function M.toggle()
	if not context.state.runtime.timer then
		M.start()
		return
	end

	if context.state.runtime.running then
		M.stop()
	else
		M.start()
	end
end

function M.status()
	return context.state.runtime.running == true
end

function M.state()
	return context.state
end

function M.events()
	return context.events
end

return M
