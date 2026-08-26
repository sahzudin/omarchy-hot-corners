local M = {}

local context = nil

local cache = {
	zone = nil,
	bindings = nil,

	exit_zone = nil,
	exit_binding = nil,
}

local function clear_cache()
	cache.zone = nil
	cache.bindings = nil

	cache.exit_zone = nil
	cache.exit_binding = nil
end

local function get_state()
	return context.state
end

local function get_config()
	return context.config
end

function M.init(ctx)
	context = ctx
	clear_cache()
end

function M.reload(ctx)
	context = ctx
	clear_cache()
end

function M.clear_cache()
	clear_cache()
end

function M.set_modifiers(modifiers)
	local state = get_state()

	if type(modifiers) ~= "table" then
		return
	end

	for key, value in pairs(modifiers) do
		if state.modifiers[key] ~= nil then
			state.modifiers[key] = value == true
		end
	end

	clear_cache()
end

local function modifiers_match(required)
	if not required then
		return true
	end

	local modifiers = get_state().modifiers

	for key, value in pairs(required) do
		if modifiers[key] ~= value then
			return false
		end
	end

	return true
end

local function get_zone_bindings(zone)
	local config = get_config()

	if not config or type(config.binds) ~= "table" then
		return nil
	end

	local binds = config.binds[zone]

	if type(binds) ~= "table" then
		return nil
	end

	return binds
end

function M.get_bindings(zone)
	if cache.zone == zone and cache.bindings then
		local copy = {}
		for i, v in ipairs(cache.bindings) do
			copy[i] = v
		end
		return copy
	end

	cache.zone = zone
	cache.bindings = {}

	local binds = get_zone_bindings(zone)

	if not binds then
		return {}
	end

	for _, binding in ipairs(binds) do
		if type(binding) == "table" and not binding.exit and modifiers_match(binding.modifiers) then
			table.insert(cache.bindings, binding)
		end
	end

	local copy = {}
	for i, v in ipairs(cache.bindings) do
		copy[i] = v
	end
	return copy
end

function M.get_active_binding(zone)
	local bindings = M.get_bindings(zone)

	return bindings[1]
end

function M.get_exit_binding(zone)
	if cache.exit_zone == zone then
		return cache.exit_binding
	end

	cache.exit_zone = zone
	cache.exit_binding = nil

	local binds = get_zone_bindings(zone)

	if not binds then
		return nil
	end

	for _, binding in ipairs(binds) do
		if type(binding) == "table" and binding.exit and modifiers_match(binding.modifiers) then
			cache.exit_binding = binding
			return binding
		end
	end

	return nil
end

function M.find_by_id(id)
	local config = get_config()

	if not config or not config.binds then
		return nil
	end

	for _, binds in pairs(config.binds) do
		for _, binding in ipairs(binds) do
			if binding.id == id then
				return binding
			end
		end
	end

	return nil
end

function M.remove(id)
	local config = get_config()

	if not config or not config.binds then
		return false
	end

	for zone, binds in pairs(config.binds) do
		for index = #binds, 1, -1 do
			if binds[index].id == id then
				table.remove(binds, index)

				clear_cache()

				if #binds == 0 then
					config.binds[zone] = nil
				end

				return true
			end
		end
	end

	return false
end

return M
