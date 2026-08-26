local M = {}

M._VERSION = "0.12.3"

local path = (...):gsub("%.init$", "")

local Core = require(path .. ".core")
local Default = require(path .. ".config")
local Binding = require(path .. ".binding")
local Bindings = require(path .. ".bindings")
local Validator = require(path .. ".validator")
local Logger = require(path .. ".logger")
local Errors = require(path .. ".errors")
local Context = require(path .. ".context")

local context = Context.new()

local function clone(value)
	if type(value) ~= "table" then
		return value
	end

	local result = {}

	for key, item in pairs(value) do
		result[key] = clone(item)
	end

	return result
end

local function merge(target, source)
	if type(source) ~= "table" then
		return
	end

	for key, value in pairs(source) do
		if type(value) == "table" and type(target[key]) == "table" then
			merge(target[key], value)
		else
			target[key] = value
		end
	end
end

local function sort_bindings(list)
	table.sort(list, function(a, b)
		return (a.priority or 0) > (b.priority or 0)
	end)
end

context.logger = Logger
context.errors = Errors

Errors.init(Logger)

function M.setup(config)
	M.config = clone(Default)

	if type(config) == "table" then
		merge(M.config, config)
	end

	M.config.binds = M.config.binds or {}

	local valid, err = Validator.validate(M.config)

	if not valid then
		Errors.capture(err)

		error("mousetrap: invalid configuration: " .. err)
	end

	context.state = clone(require(path .. ".state").state)
	context.config = M.config

	Core.init(context)

	return M
end

function M.reload(config)
	if not M.config then
		return M.setup(config)
	end

	merge(M.config, config or {})

	local valid, err = Validator.validate(M.config)

	if not valid then
		Errors.capture(err)

		return false
	end

	context.config = M.config

	Core.reload(context)

	return true
end

function M.context()
	return context
end

function M.validate(config)
	local target = clone(Default)

	merge(target, config or {})

	return Validator.validate(target)
end

function M.logger()
	return Logger
end

function M.errors()
	return Errors.get()
end

function M.log_level(level)
	Logger.set_level(level)
end

function M.modifiers(mods)
	return function()
		Core.set_modifiers(mods)
	end
end

function M.bind(zone, callback, options)
	if not M.config then
		error("mousetrap: call setup() before bind()")
	end

	local binds = M.config.binds[zone]

	if not binds then
		binds = {}
		M.config.binds[zone] = binds
	end

	local binding = Binding.new(callback, options)

	table.insert(binds, binding)

	sort_bindings(binds)

	Bindings.clear_cache()

	return binding.id
end

function M.remove_binding(id)
	return Bindings.remove(id)
end

function M.find_binding(id)
	return Bindings.find_by_id(id)
end

function M.unbind(zone, callback)
	if not M.config or not M.config.binds[zone] then
		return
	end

	local binds = M.config.binds[zone]

	for index = #binds, 1, -1 do
		if not callback or binds[index].callback == callback then
			table.remove(binds, index)
		end
	end

	Bindings.clear_cache()
end

function M.state()
	return Core.state()
end

function M.events()
	return Core.events()
end

function M.start()
	Core.start()
end

function M.stop()
	Core.stop()
end

function M.toggle()
	Core.toggle()
end

function M.status()
	return Core.status()
end

return M
