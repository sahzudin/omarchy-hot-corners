local M = {}

local context = nil

local queue = {}

function M.init(ctx)
	context = ctx
	queue = {}
end

function M.push(name, data)
	queue[#queue + 1] = {
		name = name,
		data = data,
		time = os.time(),
	}
end

function M.pop()
	if #queue == 0 then
		return nil
	end

	local event = queue[1]

	table.remove(queue, 1)

	return event
end

function M.clear()
	queue = {}
end

function M.all()
	return queue
end

return M
